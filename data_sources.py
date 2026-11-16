"""Remote data retrieval. Fail visibly; do not invent live market quotes."""
import io
import re
from datetime import datetime, timezone
from urllib.parse import quote
import pandas as pd
import requests
from bs4 import BeautifulSoup

BETA_XLS = 'https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls'
BETA_HTML = 'https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/Betas.html'
SPREAD_URL = 'https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html'
OECD_URL = ('https://sdmx.oecd.org/public/rest/data/'
            'OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,2.0/.A..ST..S13...?startPeriod=2025')
OECD_FALLBACK_URL = ('https://sdmx.oecd.org/public/rest/data/'
                     'OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,2.0/.A..ST..S13...?startPeriod=2025')
TE_URL = 'https://tradingeconomics.com/bonds'

COUNTRIES = {
    'United States': 'USA', 'United Kingdom': 'GBR', 'Germany': 'DEU',
    'France': 'FRA', 'Japan': 'JPN', 'Canada': 'CAN', 'Australia': 'AUS',
    'Italy': 'ITA', 'Spain': 'ESP', 'Netherlands': 'NLD', 'Switzerland': 'CHE',
    'Sweden': 'SWE', 'Norway': 'NOR', 'Denmark': 'DNK', 'Finland': 'FIN',
    'Belgium': 'BEL', 'Austria': 'AUT', 'Ireland': 'IRL', 'Portugal': 'PRT',
    'Poland': 'POL', 'Czech Republic': 'CZE', 'Hungary': 'HUN', 'Greece': 'GRC',
    'Turkey': 'TUR', 'Mexico': 'MEX', 'Brazil': 'BRA', 'South Korea': 'KOR',
    'China': 'CHN', 'India': 'IND', 'Indonesia': 'IDN', 'South Africa': 'ZAF',
    'New Zealand': 'NZL', 'Singapore': 'SGP', 'Israel': 'ISR', 'Chile': 'CHL',
    'Colombia': 'COL', 'Thailand': 'THA', 'Malaysia': 'MYS', 'Philippines': 'PHL',
}
ALIASES = {'US': 'United States', 'USA': 'United States', 'UK': 'United Kingdom',
           'Britain': 'United Kingdom', 'Korea': 'South Korea',
           'Czechia': 'Czech Republic', 'Turkiye': 'Turkey', 'Türkiye': 'Turkey'}


def get(url, accept=None):
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; StudentFinanceDashboard/1.0)',
               'Accept': accept or '*/*'}
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    return r


def _tables(html):
    return pd.read_html(io.StringIO(html))


def _find_beta_table(tables):
    for t in tables:
        t.columns = [' '.join(str(x) for x in c) if isinstance(c, tuple) else str(c) for c in t.columns]
        cols = list(t.columns)
        industry = next((c for c in cols if 'industry name' in c.lower()), None)
        beta = next((c for c in cols if 'unlevered beta' in c.lower() and 'corrected' not in c.lower()), None)
        if industry and beta:
            out = t[[industry, beta]].copy()
            out.columns = ['industry', 'beta_unlevered']
            out['industry'] = out['industry'].astype(str).str.strip()
            out['beta_unlevered'] = pd.to_numeric(out['beta_unlevered'], errors='coerce')
            out = out.dropna(subset=['beta_unlevered'])
            out = out[~out['industry'].str.lower().isin(['total market', 'total market (without financials)'])]
            if len(out) >= 20:
                return dict(zip(out['industry'], out['beta_unlevered'].astype(float)))
    raise ValueError('Could not identify the Industry Name and Unlevered beta columns.')


def fetch_betas():
    errors = []
    try:
        r = get(BETA_XLS)
        raw = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)
        tables = []
        for sheet in raw.values():
            for i in range(min(len(sheet), 35)):
                vals = ' '.join(sheet.iloc[i].astype(str).str.lower().tolist())
                if 'industry name' in vals and 'unlevered beta' in vals:
                    t = sheet.iloc[i+1:].copy()
                    t.columns = sheet.iloc[i].astype(str).tolist()
                    tables.append(t)
                    break
        return {'data': _find_beta_table(tables), 'source': BETA_XLS, 'as_of': 'See dataset header (typically Jan 2026)', 'status': 'live'}
    except Exception as e:
        errors.append(f'Excel: {e}')
    try:
        r = get(BETA_HTML)
        data = _find_beta_table(_tables(r.text))
        date = re.search(r'(?:Date of Analysis|Data used is as of)\s*:?\s*(?:Data used is as of\s*)?([A-Za-z]+\s+20\d\d)',
                         BeautifulSoup(r.text, 'html.parser').get_text(' ', strip=True), re.I)
        return {'data': data, 'source': BETA_HTML, 'as_of': date.group(1) if date else 'See source page', 'status': 'live (HTML fallback)'}
    except Exception as e:
        raise RuntimeError('Damodaran beta sources unavailable. ' + '; '.join(errors) + f'; HTML: {e}') from e


def fetch_spread():
    r = get(SPREAD_URL)
    soup = BeautifulSoup(r.text, 'html.parser')
    for row in soup.select('tr'):
        cells = [c.get_text(' ', strip=True) for c in row.find_all(['td', 'th'])]
        for ix, cell in enumerate(cells):
            if re.search(r'Baa2\s*/\s*BBB\b', cell, re.I):
                # FIRST matching rating belongs to the large nonfinancial firm table.
                for next_cell in cells[ix+1:ix+3]:
                    m = re.search(r'(\d+(?:\.\d+)?)\s*%', next_cell)
                    if m:
                        text = soup.get_text(' ', strip=True)
                        d = re.search(r'Data used is as of\s+([A-Za-z]+\s+20\d\d)', text, re.I)
                        return {'data': float(m.group(1))/100, 'source': SPREAD_URL,
                                'as_of': d.group(1) if d else 'See source page', 'status': 'live'}
    raise ValueError('Could not locate Baa2/BBB large nonfinancial firms row on Damodaran website.')


def fetch_oecd_taxes():
    """Latest combined statutory CIT rates from the OECD SDMX 2.0 dataset.

    Public OECD endpoint documented by its Data Explorer (July 2026).
    Parse CSV column labels defensively; reject unexpected measures/series.
    """
    url = OECD_URL + '&dimensionAtObservation=AllDimensions'
    r = get(url, accept='csvfile')
    if not r.content:
        raise ValueError('Empty response from OECD SDMX API')
    try:
        df = pd.read_csv(io.BytesIO(r.content), low_memory=False)
    except Exception as e:
        raise ValueError(f'OECD did not return CSV ({r.text[:160]!r}): {e}') from e
    df.columns = [str(c).strip().upper().replace(' ', '_') for c in df.columns]
    required = ('REF_AREA', 'TIME_PERIOD', 'OBS_VALUE')
    if not all(c in df.columns for c in required):
        raise ValueError(f'Unexpected OECD response fields: {list(df.columns)[:20]}. Response begins: {r.text[:110]!r}')
    # Query selects the statutory (ST) combined general-government (S13)
    # corporate tax series; explicitly exclude any other observations if present.
    if 'TARGETING' in df.columns:
        df = df[df['TARGETING'].astype(str).str.upper() == 'ST']
    if 'INSTITUTIONAL_SECTOR' in df.columns:
        df = df[df['INSTITUTIONAL_SECTOR'].astype(str).str.upper() == 'S13']
    if 'MEASURE' in df.columns and df['MEASURE'].nunique() > 1:
        raise ValueError(f'OECD returned multiple measures: {df["MEASURE"].unique().tolist()}')
    df['OBS_VALUE'] = pd.to_numeric(df['OBS_VALUE'], errors='coerce')
    df['TIME_PERIOD'] = pd.to_numeric(df['TIME_PERIOD'], errors='coerce')
    df = df.dropna(subset=['OBS_VALUE', 'TIME_PERIOD']).sort_values('TIME_PERIOD')
    out = {}
    for country, iso in COUNTRIES.items():
        rows = df[df['REF_AREA'].astype(str).str.upper() == iso]
        if not rows.empty:
            row = rows.iloc[-1]
            value = float(row['OBS_VALUE'])
            if 0 <= value <= 100:
                out[country] = {'rate': value / 100, 'year': int(row['TIME_PERIOD'])}
    if 'United States' not in out or len(out) < 10:
        raise ValueError(f'OECD returned only {len(out)} recognized countries; check API response and series selection')
    return {'data': out, 'source': url,
            'as_of': f"Latest country observations through {max(x['year'] for x in out.values())}",
            'status': 'live'}


def _normalize(name):
    n = re.sub(r'\s+', ' ', name.strip())
    return ALIASES.get(n, n)


def _extract_te_table(html):
    """Try conventional HTML tables and embedded JSON quote data, without guessing."""
    result = {}
    try:
        tables = _tables(html)
    except (ValueError, ImportError):
        tables = []
    for t in tables:
        t.columns = [' '.join(str(x) for x in c) if isinstance(c, tuple) else str(c) for c in t.columns]
        cols = list(t.columns)
        name_col = next((c for c in cols if 'country' in c.lower() or c.strip().lower() == 'name'), None)
        yield_col = next((c for c in cols if c.strip().lower() in ('yield', 'last', 'price', 'value')), None)
        if not name_col or not yield_col:
            continue
        date_col = next((c for c in cols if c.strip().lower() in ('date', 'time', 'lastupdate')), None)
        for _, row in t.iterrows():
            name = _normalize(str(row[name_col]))
            name = re.sub(r'\s+(10Y|10 Year|10-year).*$', '', name, flags=re.I).strip()
            if name not in COUNTRIES:
                continue
            match = re.search(r'-?\d+(?:\.\d+)?', str(row[yield_col]).replace(',', ''))
            if match:
                val = float(match.group())
                if -10 < val < 100:
                    result[name] = {'yield': val/100,
                                    'date': str(row[date_col]) if date_col else 'Source webpage; timestamp unavailable'}
    # Some versions of the public page contain serialized quote objects, not
    # <table> markup. Parse only complete objects with explicit Country and Last.
    import json
    for m in re.finditer(r'\{[^{}]{0,2000}\"Country\"\s*:\s*\"[^\"]+\"[^{}]{0,2000}\}', html):
        try:
            obj = json.loads(m.group())
        except (ValueError, TypeError):
            continue
        name = _normalize(str(obj.get('Country', '')).strip())
        title = str(obj.get('Name', obj.get('Symbol', ''))).lower()
        if name not in COUNTRIES or ('bond' not in title and '10y' not in title and '10 year' not in title):
            continue
        try:
            val = float(str(obj['Last']).replace(',', ''))
        except (ValueError, TypeError, KeyError):
            continue
        if -10 < val < 100:
            result[name] = {'yield': val/100,
                            'date': str(obj.get('Date') or obj.get('LastUpdate') or 'Source webpage; timestamp unavailable')}
    return result


def fetch_yields():
    """Attempt public TE table/embedded quotes; fail transparently if restricted.

    Trading Economics also has an official authenticated bonds API, but the
    assignment specifies no API key, so the app never assumes credentials.
    """
    r = get(TE_URL)
    result = _extract_te_table(r.text)
    if 'United States' not in result or len(result) < 2:
        raise ValueError('Trading Economics did not expose accessible live 10-year yield quotes in HTML or embedded JSON. This is a site access limitation, not a Streamlit deployment failure. Open https://tradingeconomics.com/bonds and manually override the U.S. and target-country yields with verified dated quotes.')
    return {'data': result, 'source': TE_URL,
            'as_of': 'Source quote date per country; fetched now', 'status': 'live'}


def try_fetch(loader):
    try:
        result = loader()
        result['fetched_at_utc'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        return result
    except Exception as e:
        return {'data': None, 'source': {'fetch_betas': BETA_XLS, 'fetch_spread': SPREAD_URL,
                'fetch_oecd_taxes': OECD_URL, 'fetch_yields': TE_URL}[loader.__name__],
                'as_of': 'Unavailable', 'status': 'ERROR', 'error': str(e),
                'fetched_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
