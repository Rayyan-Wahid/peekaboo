"""Local, read-only results dashboard and clearly labeled saved-trace replay."""
import json
from pathlib import Path

import altair as alt
import joblib
import numpy as np
import pandas as pd
import streamlit as st

from peekaboo.defense import jitter_trace
from peekaboo.features import feature_vector, load_trace

ROOT = Path(__file__).resolve().parents[2]
st.set_page_config(page_title='Peekaboo | Traffic privacy lab', page_icon='◉', layout='wide')
st.markdown('''<style>
 .block-container {max-width:1200px;padding-top:2rem;}
 [data-testid="stMetric"] {background:#122332;border:1px solid #29404e;border-radius:12px;padding:16px;}
 </style>''', unsafe_allow_html=True)
st.caption('PEEKABOO / HTTPS TRAFFIC PRIVACY LAB')
st.title('What can encrypted traffic reveal?')
st.write('Explore website predictions from traffic patterns, then see what simulated timing jitter changes.')

latest = ROOT / 'reports/latest.json'
if not latest.exists():
    st.info('The experiment has not finished yet. Run feature extraction and the experiment to populate this dashboard.')
    st.code('python -m peekaboo extract\npython -m peekaboo experiment')
    st.stop()
run_name = json.loads(latest.read_text())['run_name']
report = json.loads((ROOT / 'reports' / run_name / 'results.json').read_text())
if report['status'] != 'complete':
    st.info('Experiment in progress. Results will appear after all comparisons complete.')
    st.stop()

st.caption(f"Local experiment · {len(report['classes'])} known websites · "
           f"{sum(report['split_counts'].values())} accepted traces · {run_name}")
overview, defense, replay, method = st.tabs(['Baseline results', 'Defense comparison', 'Replay a trace', 'How it works'])

with overview:
    baseline = report['baseline']['test']
    a, b, c, d = st.columns(4)
    a.metric('Test accuracy', f"{baseline['accuracy']:.1%}")
    b.metric('Macro F1', f"{baseline['macro_f1']:.3f}")
    c.metric('Held-out test traces', baseline['samples'])
    d.metric('Uniform guess expectation', f"{report['uniform_guess_expected_accuracy']:.0%}")
    st.write('The Random Forest was trained on October 28–29 and tuned on October 30. '
             'The October 31 captures were held out for final evaluation.')
    st.subheader('Which websites get confused?')
    classes = report['classes']
    confusion = pd.DataFrame(report['baseline']['test']['confusion_matrix'], index=classes, columns=classes)
    heat = confusion.rename_axis('Actual').reset_index().melt(id_vars='Actual', var_name='Predicted', value_name='Visits')
    chart = alt.Chart(heat).mark_rect().encode(
        x=alt.X('Predicted:N', sort=classes, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Actual:N', sort=classes), color=alt.Color('Visits:Q', scale=alt.Scale(scheme='tealblues')),
        tooltip=['Actual', 'Predicted', 'Visits']).properties(height=480)
    st.altair_chart(chart, width='stretch')
    with st.expander('Per-website results and split counts'):
        per_class = pd.DataFrame({site: baseline['per_class'][site] for site in classes}).T
        st.dataframe(per_class, width='stretch')
        st.dataframe(pd.DataFrame(report['class_counts']), width='stretch')

with defense:
    st.subheader('Can delays make recognition harder?')
    st.write('Lower classification accuracy means more privacy in this experiment. '
             'The adaptive classifier is retrained on the same kind of jitter it later sees.')
    records = []
    for item in report['defense']:
        for key, label in [('fixed', 'Original classifier'), ('adaptive', 'Retrained classifier')]:
            records.append({'Jitter bound (ms)': item['max_delay_ms'], 'Classifier': label,
                'Accuracy': item[key]['test']['accuracy'], 'Macro F1': item[key]['test']['macro_f1'],
                'Seed': item['seed'],
                'Mean simulated packet delay (ms)': item['test_simulated_costs']['mean_packet_delay_ms'],
                'Mean simulated trace extension (ms)': item['test_simulated_costs']['trace_finish_extension_ms']})
    frame = pd.DataFrame(records)
    summary = frame.groupby(['Jitter bound (ms)', 'Classifier'], as_index=False).mean(numeric_only=True).drop(columns='Seed')
    line = alt.Chart(summary).mark_line(point=True).encode(
        x=alt.X('Jitter bound (ms):Q'),
        y=alt.Y('Accuracy:Q', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format='%')),
        color='Classifier:N', tooltip=['Jitter bound (ms)', 'Classifier', alt.Tooltip('Accuracy:Q', format='.1%')])
    st.altair_chart(line, width='stretch')
    st.dataframe(summary, hide_index=True, width='stretch')
    st.info('Timestamp simulation only. Captured byte overhead is 0% by construction. '
            'These delay values are not measured page-load times. Nonzero bounds use three simulation seeds.')

with replay:
    st.subheader('Replay a held-out capture')
    st.write('This uses an existing October 31 capture. It does not open a website or make a fresh network measurement.')
    rows = [json.loads(line) for line in (ROOT / 'data/processed/analysis-v1/visits.jsonl').read_text().splitlines()]
    test_rows = [row for row in rows if row['split'] == 'test']
    selected = st.selectbox('Saved test trace', range(len(test_rows)),
        format_func=lambda i: f"{test_rows[i]['site_id']} · {test_rows[i]['visit_id'][:8]}")
    bound = st.select_slider('Simulated jitter bound (ms)', options=report['config']['defense']['max_delay_ms'], value=0)
    if st.button('Predict this saved trace', type='primary'):
        row = test_rows[selected]
        trace = load_trace(ROOT / 'data/processed/analysis-v1/traces' / (row['visit_id'] + '.npz'))
        trace, costs = jitter_trace(trace, bound, report['config']['defense']['seeds'][0], row['sha256'])
        vector = feature_vector(trace)
        fixed = joblib.load(ROOT / 'models' / run_name / 'baseline.joblib')
        models = [('Original classifier', fixed)]
        if bound:
            models.append(('Retrained classifier', joblib.load(ROOT / 'models' / run_name / f'adaptive-{bound}ms.joblib')))
        for label, bundle in models:
            values = np.asarray([[vector[name] for name in bundle['features']]])
            probabilities = bundle['model'].predict_proba(values)[0]
            scores = pd.DataFrame({'Website': bundle['classes'], 'Forest score': probabilities}).sort_values('Forest score', ascending=False)
            predicted = scores.iloc[0]['Website']
            st.write(f"**{label}: {predicted}** · actual website: {row['site_id']}")
            st.dataframe(scores.head(3), hide_index=True, width='stretch')
        st.caption('Forest scores are not calibrated confidence. The model always chooses among the 20 known sites.')

with method:
    st.subheader('Traffic → metadata → model → comparison')
    st.write('1. Keep only accepted captures and verify their hashes.\n'
             '2. Remove plaintext CONNECT exchanges and retain TCP payload sizes, directions, and timing.\n'
             '3. Build 107 numerical features; labels, dates, addresses, ports, and hostnames are excluded.\n'
             '4. Tune a 300-tree Random Forest on validation data.\n'
             '5. Apply bounded per-flow/direction delays and test original versus retrained classifiers.')
    st.subheader('Limits of this experiment')
    for limitation in report['limitations']:
        st.write('• ' + limitation)
    st.caption('A fresh controlled capture can be classified with the CLI predict command. '
               'The replay above is a demonstration of saved data, not a fresh visit.')
