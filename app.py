import io
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import plotly.express as px
import streamlit as st
from calculations import calculate
from data_sources import COUNTRIES, try_fetch, fetch_betas, fetch_spread, fetch_oecd_taxes, fetch_yields

st.set_page_config(page_title='International Cost of Capital | Kellogg', page_icon='📊', layout='wide', initial_sidebar_state='expanded')

PURPLE = '#4F2582'
st.markdown('''<style>
.stApp { background: #F8F7FA; color: #262036; }
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E9E3F0; }
.block-container { max-width: 1450px; padding-top: 1.8rem; }
h1,h2,h3 { color: #321451 !important; letter-spacing: -.025em; }
h1 { font-weight: 750 !important; }
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #E6E0EF; border-radius: 15px; padding: 16px 19px; box-shadow: 0 3px 14px rgba(47,29,79,.04); }
[data-testid="stMetricLabel"] { color: #62586D; }
[data-testid="stMetricValue"] { color: #4F2582; }
.stButton button[kind="primary"] { background: #4F2582; border-color: #4F2582; }
.kicker { letter-spacing: .18em; text-transform: uppercase; color: #765A9D; font-size: 12px; font-weight: 750; }
.hero { background: linear-gradient(115deg, #381667 0%, #602C9E 100%); color: white; padding: 25px 30px; border-radius: 19px; margin-bottom: 20px; }
.hero h1 { color: #FFFFFF !important; margin: 5px 0 7px 0; font-size: 2.2rem; }
.hero p { color: #EDE3FA; margin-bottom: 0; }
.hero .kicker { color: #E1C9FF; }
.tagline { color: #74657E; font-size: 14px; margin-bottom: 10px; }
</style>''', unsafe_allow_html=True)

@st.cache_data(ttl=6*60*60, show_spinner=False)
def load_data():
    return { 'betas': try_fetch(fetch_betas), 'spread': try_fetch(fetch_spread),
             'taxes': try_fetch(fetch_oecd_taxes), 'yields': try_fetch(fetch_yields) }

st.markdown('<div class="hero"><div class="kicker">Kellogg · International Finance</div><h1>International Cost of Capital</h1><p>Compare project financing costs across currencies with transparent assumptions and source-linked market data.</p></div>', unsafe_allow_html=True)

head_left, head_right = st.columns([5, 1])
with head_right:
    if st.button('↻ Refresh sources', use_container_width=True, help='Clears the 6-hour data cache and attempts new source downloads.'):
        load_data.clear()
        st.rerun()
with st.spinner('Loading latest source data...'):
    sources = load_data()

# A user-maintained CSV is a documented alternative when the OECD / TE feeds
# reject automated queries. It can live in the GitHub repository or be uploaded
# during a session. Blank cells do not override existing data.
CSV_COLS = ('country', 'corporate_tax_rate_pct', 'tax_as_of',
            'government_10y_yield_pct', 'yield_as_of',
            'tax_source_url', 'yield_source_url')

def apply_manual_csv(base_sources, csv_file, filename):
    df = pd.read_csv(csv_file, dtype=str, keep_default_na=False).fillna('')
    if any(c not in df.columns for c in CSV_COLS):
        raise ValueError('CSV must include: ' + ', '.join(CSV_COLS))
    if df['country'].duplicated().any():
        raise ValueError('CSV contains duplicate country names.')
    updated = {k: dict(v) for k, v in base_sources.items()}
    used = {'taxes': [], 'yields': []}
    for _, r in df.iterrows():
        name = r['country'].strip()
        if name not in COUNTRIES:
            if name: raise ValueError(f'Country not supported: {name}')
            continue
        for dataset, value_col, date_col, url_col, out_key, factor in [
            ('taxes', 'corporate_tax_rate_pct', 'tax_as_of', 'tax_source_url', 'rate', 100),
            ('yields', 'government_10y_yield_pct', 'yield_as_of', 'yield_source_url', 'yield', 100)]:
            raw = r[value_col].strip()
            if not raw:
                continue
            value = float(raw)
            if not (0 <= value <= 100) if dataset == 'taxes' else not (-10 < value < 100):
                raise ValueError(f'Unreasonable {value_col} for {name}: {value}')
            if not r[date_col].strip() or not r[url_col].strip():
                raise ValueError(f'{name}: {value_col} requires both source date and source URL.')
            current = updated[dataset]
            current['data'] = dict(current.get('data') or {})
            current['data'][name] = {out_key: value / factor,
                                     'date': r[date_col].strip(),
                                     'year': r[date_col].strip(),
                                     'source_url': r[url_col].strip()}
            used[dataset].append(name)
    for dataset, countries in used.items():
        if countries:
            obj = updated[dataset]
            obj['status'] = 'MANUAL CSV' if base_sources[dataset]['data'] is None else 'LIVE + MANUAL CSV'
            obj['source'] = filename
            obj['as_of'] = 'See per-country dates in manually maintained CSV'
            obj['error'] = ''
    return updated, used

with st.sidebar:
    with st.expander('Import verified market data (CSV)', expanded=False):
        st.caption('Upload a filled CSV, or commit market_data.csv to GitHub for automatic reuse. Entries must include their original source URL and observation date. Data are labeled manual, never live.')
        uploaded_market_csv = st.file_uploader('Upload market data', type=['csv'], key='market_csv')
        st.download_button('Download blank CSV template',
                           data='country,corporate_tax_rate_pct,tax_as_of,government_10y_yield_pct,yield_as_of,tax_source_url,yield_source_url\nUnited States,,,,,,\nUnited Kingdom,,,,,,\n',
                           file_name='market_data.csv', mime='text/csv')

try:
    if uploaded_market_csv is not None:
        sources, csv_used = apply_manual_csv(sources, uploaded_market_csv, uploaded_market_csv.name)
    elif Path('market_data.csv').exists():
        sources, csv_used = apply_manual_csv(sources, 'market_data.csv', 'market_data.csv (GitHub)')
    else:
        csv_used = {'taxes': [], 'yields': []}
except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
    st.error('Market-data CSV error: ' + str(exc))
    csv_used = {'taxes': [], 'yields': []}
if any(csv_used.values()):
    st.info('Using manually verified CSV data for: ' + '; '.join(
        dataset + ' (' + ', '.join(names) + ')' for dataset, names in csv_used.items() if names) +
        '. Source dates/URLs should be checked against the original publications.')

betas = sources['betas']['data'] or {}
taxes = sources['taxes']['data'] or {}
yields = sources['yields']['data'] or {}
spread_data = sources['spread']['data']

with st.sidebar:
    st.markdown('### Project settings')
    industries = sorted(set(betas) | {'Software (System & Application)'})
    default_industry = 'Software (System & Application)'
    industry = st.selectbox('Industry', industries, index=industries.index(default_industry))
    country = st.selectbox('Target country / currency', list(COUNTRIES), index=0)
    tax_choice = st.segmented_control('Project tax rate', ['U.S. tax', 'Target-country tax'], default='U.S. tax')
    erp_pct = st.number_input('Equity risk premium (%)', min_value=0.0, max_value=50.0, value=6.5, step=0.25, format='%.2f')
    debt_pct = st.slider('Target debt financing (%)', 0, 95, 30, step=5)
    st.divider()
    st.markdown('### Data inputs & overrides')
    st.caption('Each checkbox replaces only its corresponding source value. Missing source values require a manual entry.')

    def number_override(label, key, source_value, format='%.3f', step=0.1, max_value=100.0):
        on = st.checkbox('Manual ' + label, value=False, key='flag_' + key,
                         disabled=False)
        default = float(source_value) if source_value is not None else 0.0
        if on or source_value is None:
            val = st.number_input(label, value=default, min_value=0.0, max_value=max_value,
                                  step=step, format=format, key='value_' + key)
            return val, 'manual' if on else 'manual required', True
        st.caption(f'{label}: {default:{format[1:]}} (auto)')
        return default, 'manual CSV' if any(csv_used.values()) and key in ('tax_us', 'tax_foreign', 'yield_us', 'yield_foreign') and ((key.startswith('tax') and (('United States' if key == 'tax_us' else country) in csv_used['taxes'])) or (key.startswith('yield') and (('United States' if key == 'yield_us' else country) in csv_used['yields']))) else 'live', False

    beta_val, beta_status, _ = number_override('Unlevered beta', 'beta', betas.get(industry), '%.3f', 0.01, 20.0)
    tax_us = taxes.get('United States', {}).get('rate')
    tax_foreign = taxes.get(country, {}).get('rate')
    rate_us, us_tax_status, _ = number_override('U.S. tax rate (%)', 'tax_us', None if tax_us is None else tax_us*100, '%.2f', 0.25)
    rate_foreign, foreign_tax_status, _ = number_override('Target tax rate (%)', 'tax_foreign', None if tax_foreign is None else tax_foreign*100, '%.2f', 0.25)
    spread_us, spread_status, _ = number_override('USD BBB spread (%)', 'spread_us', None if spread_data is None else spread_data*100, '%.3f', 0.05)
    yield_us = yields.get('United States', {}).get('yield')
    yield_foreign = yields.get(country, {}).get('yield')
    y_us, y_us_status, _ = number_override('U.S. 10-year yield (%)', 'yield_us', None if yield_us is None else yield_us*100, '%.3f', 0.05)
    y_foreign, y_foreign_status, _ = number_override('Target 10-year yield (%)', 'yield_foreign', None if yield_foreign is None else yield_foreign*100, '%.3f', 0.05)
    local_override_on = st.checkbox('Manual target-country BBB spread', value=False)
    local_spread = st.number_input('Target BBB spread (%)', min_value=0.0, max_value=100.0,
                                    value=float(spread_us), step=0.05, format='%.3f',
                                    disabled=not local_override_on)
    st.caption('When off, the target spread is derived from U.S. BBB borrowing cost and the government-yield ratio.')

if country == 'United States':
    # Same currency must always have identical market inputs; use US yield/spread for the comparison.
    y_foreign = y_us
    if not local_override_on:
        local_spread = spread_us

tax_pct = rate_us if tax_choice == 'U.S. tax' else rate_foreign
foreign_override = local_spread/100 if local_override_on else None

try:
    result = calculate(beta_val, y_us/100, y_foreign/100, erp_pct/100, debt_pct/100,
                       tax_pct/100, spread_us/100, foreign_override)
except ValueError as e:
    st.error(str(e)); st.stop()

missing = [name for name, doc in sources.items() if doc['status'] == 'ERROR']
if missing:
    st.warning('Some data sources could not be loaded: ' + ', '.join(missing) + '. Check the **Data sources** tab and supply manual values where needed. Values displayed as 0.000 when unavailable are placeholders, NOT market observations.')
    manual_missing = {'betas': beta_status != 'live', 'spread': spread_status != 'live',
                      'taxes': us_tax_status != 'live' or foreign_tax_status != 'live',
                      'yields': y_us_status != 'live' or y_foreign_status != 'live'}
    if any((name == 'betas' and beta_status == 'manual required') or
           (name == 'spread' and spread_status == 'manual required') or
           (name == 'taxes' and (us_tax_status == 'manual required' or foreign_tax_status == 'manual required')) or
           (name == 'yields' and (y_us_status == 'manual required' or y_foreign_status == 'manual required'))
           for name in missing):
        st.error('At least one required source value is unavailable. Enter and verify manual data in the sidebar. Results below are **illustrative only** until those inputs are replaced.')

st.markdown(f'<div class="tagline">{industry} &nbsp; · &nbsp; United States versus {country} &nbsp; · &nbsp; {tax_choice} &nbsp; · &nbsp; {debt_pct}% debt / {100-debt_pct}% equity</div>', unsafe_allow_html=True)

st.markdown('### Cost of capital overview')
left, right = st.columns(2, gap='large')
with left:
    st.markdown('#### U.S. dollar (USD)')
    c1,c2,c3 = st.columns(3)
    c1.metric('Cost of equity', f'{result.cost_equity_usd*100:.2f}%')
    c2.metric('Cost of debt', f'{result.cost_debt_usd*100:.2f}%')
    c3.metric('WACC', f'{result.wacc_usd*100:.2f}%')
with right:
    st.markdown(f'#### {country} (local currency)')
    c1,c2,c3 = st.columns(3)
    c1.metric('Cost of equity', f'{result.cost_equity_local*100:.2f}%')
    c2.metric('Cost of debt', f'{result.cost_debt_local*100:.2f}%')
    c3.metric('WACC', f'{result.wacc_local*100:.2f}%', delta=f'{(result.wacc_local-result.wacc_usd)*100:+.2f} pp', delta_color='off')

st.caption(f'Levered beta: {result.beta_levered:.3f}  ·  Project tax rate: {tax_pct:.2f}%  ·  USD BBB spread: {spread_us:.3f}%  ·  Target BBB spread: {result.spread_local*100:.3f}% ({"manual" if local_override_on else "calculated"})')

tab_results, tab_industries, tab_method, tab_sources, tab_checks = st.tabs(['Results & comparison', 'All industries', 'Methodology', 'Data sources', 'Verification'])

with tab_results:
    chart_df = pd.DataFrame([
        {'Currency': 'USD', 'Metric': 'Equity cost', 'Rate (%)': result.cost_equity_usd*100},
        {'Currency': 'USD', 'Metric': 'Debt cost', 'Rate (%)': result.cost_debt_usd*100},
        {'Currency': 'USD', 'Metric': 'WACC', 'Rate (%)': result.wacc_usd*100},
        {'Currency': country, 'Metric': 'Equity cost', 'Rate (%)': result.cost_equity_local*100},
        {'Currency': country, 'Metric': 'Debt cost', 'Rate (%)': result.cost_debt_local*100},
        {'Currency': country, 'Metric': 'WACC', 'Rate (%)': result.wacc_local*100},
    ])
    fig = px.bar(chart_df, x='Metric', y='Rate (%)', color='Currency', barmode='group', text_auto='.2f',
                 color_discrete_sequence=[PURPLE, '#16A1A0'])
    fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                      legend_title_text='', margin=dict(l=10,r=10,t=25,b=10), font=dict(color='#332741'))
    st.plotly_chart(fig, use_container_width=True)
    detail = pd.DataFrame({
        'Metric': ['Government 10-year yield', 'Unlevered beta', 'Levered beta', 'Equity risk premium', 'Cost of equity', 'BBB borrowing spread', 'Pre-tax cost of debt', 'After-tax cost of debt', 'WACC'],
        'USD': [f'{y_us:.3f}%', f'{beta_val:.3f}', f'{result.beta_levered:.3f}', f'{erp_pct:.2f}%', f'{result.cost_equity_usd*100:.3f}%', f'{spread_us:.3f}%', f'{result.cost_debt_usd*100:.3f}%', f'{result.cost_debt_usd*(1-tax_pct/100)*100:.3f}%', f'{result.wacc_usd*100:.3f}%'],
        country: [f'{y_foreign:.3f}%', f'{beta_val:.3f}', f'{result.beta_levered:.3f}', f'{erp_pct:.2f}%', f'{result.cost_equity_local*100:.3f}%', f'{result.spread_local*100:.3f}%', f'{result.cost_debt_local*100:.3f}%', f'{result.cost_debt_local*(1-tax_pct/100)*100:.3f}%', f'{result.wacc_local*100:.3f}%']})
    st.dataframe(detail, use_container_width=True, hide_index=True)
    st.download_button('Download selected-project comparison (CSV)', detail.to_csv(index=False).encode(),
                       file_name='cost_of_capital_comparison.csv', mime='text/csv')

with tab_industries:
    st.markdown('#### Industry-wide cost of capital')
    st.caption('All Damodaran industries use your current country, ERP, leverage, tax choice, yields, and spread assumptions. Only the industry unlevered beta varies. The selected-industry manual beta override is applied to that industry only.')
    rows = []
    for name, unlevered in sorted(betas.items()):
        b = beta_val if name == industry and beta_status == 'manual' else unlevered
        r = calculate(float(b), y_us/100, y_foreign/100, erp_pct/100, debt_pct/100, tax_pct/100, spread_us/100, foreign_override)
        rows.append({'Industry': name, 'Unlevered beta': b, 'Levered beta': r.beta_levered,
                     'USD cost equity (%)': r.cost_equity_usd*100, 'Local cost equity (%)': r.cost_equity_local*100,
                     'USD debt cost (%)': r.cost_debt_usd*100, 'Local debt cost (%)': r.cost_debt_local*100,
                     'USD WACC (%)': r.wacc_usd*100, 'Local WACC (%)': r.wacc_local*100})
    if rows:
        df_all = pd.DataFrame(rows)
        st.dataframe(df_all, use_container_width=True, hide_index=True,
                     column_config={c: st.column_config.NumberColumn(c, format='%.3f') for c in df_all.select_dtypes('number').columns})
        st.download_button('Download all industries (CSV)', df_all.to_csv(index=False).encode(),
                           file_name='all_industries_cost_of_capital.csv', mime='text/csv')
    else:
        st.info('Full industry comparison becomes available once the Damodaran table is fetched. Single-industry manual calculation remains available.')

with tab_method:
    st.markdown('#### Finance formulas and assumptions')
    st.latex(r'D/E = w_D/(1-w_D)')
    st.latex(r'\beta_L = \beta_U [1+(1-T)D/E]')
    st.latex(r'K_{e,USD}=Y_{US}+\beta_L ERP \qquad K_{e,local}=Y_{local}+\beta_L ERP')
    st.latex(r'K_{d,USD}=Y_{US}+s_{BBB,USD}')
    st.latex(r'K_{d,local}^{auto}=(1+K_{d,USD})\frac{1+Y_{local}}{1+Y_{US}}-1')
    st.latex(r's_{BBB,local}^{auto}=K_{d,local}^{auto}-Y_{local}')
    st.latex(r'WACC=(1-w_D)K_e+w_D K_d (1-T)')
    st.info('**Assumption to validate with class notes:** Local CAPM adds the SAME ERP (in percentage points) to each country’s 10-year government yield. The local debt spread is derived by matching gross borrowing returns through the ratio of 10-year sovereign yields; it is not a quoted local BBB bond spread. The professor may specify a different conversion or country-risk model.')
    st.markdown('**Consistency rules:** The same selected project tax rate is applied to beta relevering and the debt tax shield in both currencies. The same debt weighting and ERP apply to both. United States selected as target uses the USD benchmark yield. Government bonds are treated as risk-free proxies, although sovereign credit, inflation and currency risks may matter.')
    st.markdown('**Interpretation:** Local-currency WACC is not a direct estimate of incremental project value relative to USD WACC. Cash flows must be forecast and discounted consistently in the same currency. The 10-year yields are a term-matched benchmark only insofar as the project horizon is similar.')

with tab_sources:
    st.markdown('#### Data provenance and freshness')
    records = []
    for name, item in sources.items():
        records.append({'Dataset': {'betas':'Damodaran — U.S. unlevered industry betas', 'spread':'Damodaran — Baa2/BBB large non-financial spread',
                                    'taxes':'OECD — combined statutory corporate tax', 'yields':'Trading Economics — 10-year government bonds'}[name],
                        'Status': item['status'], 'Source date': item['as_of'], 'Fetched (UTC)': item['fetched_at_utc'],
                        'Source URL': item['source'], 'Error': item.get('error', '')})
    st.dataframe(pd.DataFrame(records), hide_index=True, use_container_width=True,
                 column_config={'Source URL': st.column_config.LinkColumn('Source URL')})
    st.caption('Refresh clears the 6-hour live cache and retries sources. MANUAL CSV means verified user-entered data, not a successful live retrieval. CSV entries should include source URLs and observation dates.')
    if tax_us is not None:
        st.caption(f'OECD U.S. tax: {tax_us*100:.2f}% (year {taxes["United States"]["year"]}). ' + (f'{country}: {tax_foreign*100:.2f}% (year {taxes[country]["year"]}).' if tax_foreign is not None else f'No OECD observation found for {country}.'))
    st.markdown('Source pages: [Damodaran betas](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/Betas.html) · [Damodaran ratings](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html) · [OECD](https://www.oecd.org/en/data/datasets/corporate-income-tax-rates-database.html) · [Trading Economics](https://tradingeconomics.com/bonds)')

with tab_checks:
    st.markdown('#### Built-in mathematical verification')
    same_yield = calculate(beta_val, y_us/100, y_us/100, erp_pct/100, debt_pct/100, tax_pct/100, spread_us/100)
    zero_debt = calculate(beta_val, y_us/100, y_foreign/100, erp_pct/100, 0, tax_pct/100, spread_us/100)
    base = calculate(beta_val, y_us/100, y_foreign/100, erp_pct/100, debt_pct/100, tax_pct/100, spread_us/100)
    bumped = calculate(beta_val, y_us/100, y_foreign/100, erp_pct/100, debt_pct/100, tax_pct/100, spread_us/100, 0.03)
    tests = {
        'Equal sovereign yields → equal equity, debt, WACC (auto local spread)': all(abs(a-b) < 1e-10 for a,b in [
            (same_yield.cost_equity_usd,same_yield.cost_equity_local),
            (same_yield.cost_debt_usd,same_yield.cost_debt_local), (same_yield.wacc_usd,same_yield.wacc_local)]),
        'Zero debt → WACC equals equity cost in each currency': all(abs(a-b) < 1e-10 for a,b in [
            (zero_debt.wacc_usd,zero_debt.cost_equity_usd),(zero_debt.wacc_local,zero_debt.cost_equity_local)]),
        'Changing local spread override → USD results unchanged': all(abs(a-b) < 1e-10 for a,b in [
            (base.wacc_usd,bumped.wacc_usd),(base.cost_debt_usd,bumped.cost_debt_usd),
            (base.cost_equity_usd,bumped.cost_equity_usd)])
    }
    for label, passed in tests.items():
        st.write(('✅' if passed else '❌') + ' ' + label)
    st.caption('These are algebraic checks, not substitutes for verifying the accuracy of scraped source values and the professor’s prescribed finance formulas.')
    st.markdown('**Independent calculation template** (using currently selected inputs):')
    st.code(f'''D/E = {debt_pct/100:.4f} / {1-debt_pct/100:.4f} = {debt_pct/(100-debt_pct):.6f}
Levered beta = {beta_val:.4f} × [1 + (1 - {tax_pct/100:.4f}) × {debt_pct/(100-debt_pct):.6f}] = {result.beta_levered:.6f}
USD cost equity = {y_us:.4f}% + {result.beta_levered:.6f} × {erp_pct:.4f}% = {result.cost_equity_usd*100:.6f}%
USD debt cost = {y_us:.4f}% + {spread_us:.4f}% = {result.cost_debt_usd*100:.6f}%
USD WACC = {(1-debt_pct/100):.4f} × {result.cost_equity_usd*100:.6f}% + {debt_pct/100:.4f} × {result.cost_debt_usd*100:.6f}% × (1 - {tax_pct/100:.4f}) = {result.wacc_usd*100:.6f}%''', language='text')

payload = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'industry': industry,
           'country': country, 'tax_choice': tax_choice, 'inputs': {
               'beta_unlevered': beta_val, 'us_yield_pct': y_us, 'foreign_yield_pct': y_foreign,
               'erp_pct': erp_pct, 'debt_share_pct': debt_pct, 'tax_pct': tax_pct,
               'us_bbb_spread_pct': spread_us, 'local_bbb_spread_override_pct': local_spread if local_override_on else None},
           'results': result.to_dict(), 'sources': sources}
st.download_button('Download assumptions + source metadata + results (JSON)',
                   data=json.dumps(payload, indent=2, default=str), file_name='capital_cost_audit.json',
                   mime='application/json')
st.caption('Student-built financial analysis tool · Not investment advice · Source data requires independent verification')
