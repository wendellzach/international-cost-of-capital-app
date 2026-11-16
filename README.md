International Cost of Capital Dashboard
Kellogg-inspired Streamlit project comparing cost of equity, pre-tax cost of debt and WACC in USD and a selected country's currency, with live-source acquisition, manual overrides, all-industry comparisons, downloadable CSV/JSON exports, and algebraic verification.
Deploy on Streamlit Community Cloud
1. Create a new GitHub repository, e.g. international-cost-of-capital.
2. Upload all files, including calculations.py, data_sources.py, tests/test_calculations.py, and .streamlit/config.toml (the dot-folder is optional for the functional app).
3. In Streamlit Community Cloud, select the repository, branch main, and entry point app.py.
4. Deploy. The server requires access to the external source websites. If a website blocks requests, use the sidebar manual override and confirm values directly from its cited website.
5. Use ↻ Refresh sources to clear Streamlit's six-hour data cache and reattempt downloads.
Run locally:
pip install -r requirements.txt
streamlit run app.py
pytest -q
Data sources
- Damodaran industry unlevered betas: Excel workbook, with HTML fallback. Uses the Unlevered beta, not the cash-corrected unlevered beta, column.
- BBB corporate spread: Damodaran ratings, specifically Baa2/BBB, large non-financial firms, not the financial-services table.
- Tax: OECD 2026 corporate tax data, via its public SDMX data endpoint. Uses general-government combined statutory corporate income tax rate and latest available year for each country, not just federal tax.
- 10-year government yields: Trading Economics bonds. Page scraping may fail if the site changes its markup or blocks automation; failures are reported, and manual entries are possible. No unofficial values are silently invented.
Important reliability note: This code has been statically checked and its mathematical unit tests run locally, but live network retrieval could not be exercised in this build environment. After deploying, verify actual OECD columns and TE HTML against their current websites. The original requirement specifies "any country"; this implementation offers a broad curated country list. A country without source coverage can still be evaluated with manual inputs. Any manual placeholder of 0.000 is not a quote and must be replaced with a verified value.
Models to confirm with your instructor
Let Y_US and Y_F be 10-year government yields, ERP shared equity risk premium, wD debt weight, T one chosen project corporate income tax rate, BU industry unlevered beta, s_US the USD BBB spread.
1. D/E = wD / (1-wD)
2. BL = BU * (1 + (1-T)*D/E) (Hamada relevering)
3. Ke_US = Y_US + BL*ERP; Ke_F = Y_F + BL*ERP (same nominal ERP in percentage points)
4. Kd_US = Y_US + s_US
5. Kd_F_auto = (1+Kd_US)*(1+Y_F)/(1+Y_US)-1 (gross-yield-ratio conversion)
6. s_F_auto = Kd_F_auto-Y_F. If local BBB spread override is on, Kd_F = Y_F+s_F_manual instead.
7. WACC = (1-wD)*Ke + wD*Kd*(1-T) separately for each currency.
These are explicit modeling assumptions, not claims about what your instructor supplied. In particular, this is not a country-risk-premium model, and the target-currency BBB spread is derived rather than directly measured. Update calculations.py if the class formulas differ.
Independent calculation example (illustrative, manually chosen—not live source quotes)
- BU=1.00, US 10y=4.00%, foreign 10y=6.00%, ERP=6.50%, wD=30%, T=25%, USD BBB=1.11%.
- D/E=0.30/0.70=0.428571; BL=1*(1+0.75*0.428571)=1.32142857.
- Ke_US=4.00%+1.32142857*6.50%=12.5892857%.
- Kd_US=4.00%+1.11%=5.11%.
- WACC_US=70%*12.5892857%+30%*5.11%*(1-25%)=9.96225%.
- Ke_F=6.00%+1.32142857*6.50%=14.5892857%.
- Kd_F=(1+0.0511)*(1.06/1.04)-1 = 7.1313462% (rounded).
- s_F=Kd_F-6.00%=1.1313462%.
- WACC_F=70%*14.5892857%+30%*7.1313462%*(1-25%) ≈ 11.8171%.
Required checks
- When U.S. and foreign government bond yields are the same, both currency outputs must match if local BBB override is off.
- When debt share is zero, WACC must equal cost of equity.
- Editing only the foreign BBB spread must not affect USD results.
- Independently verify an actual, source-dated example with a spreadsheet or calculator, and check at least one scraped value on the source website.
These checks are implemented both as a Verification app tab and pytest tests.
Suggested submission checklist
- GitHub repository URL: insert after publishing
- Deployed Streamlit app URL: insert after deployment
- AI chat snapshots showing code generation and a verification exchange
- Screenshot of selected industry/country with all real data available (or labeled manual entries)
- Your own independent numeric check and description of one formula/data-choice you verified
Known limitations
Trading Economics may be script-rendered, rate-limited or access-protected. The app does not bypass those restrictions; use manual quotes if necessary. OECD SDMX structure may evolve. Country-specific government bond yield is a proxy for risk-free rate, and different local currencies can require an inflation/FX consistent ERP adjustment depending on class methodology. No investment recommendation is intended.
