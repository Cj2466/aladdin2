# Dormant pool population report (2026-09-09, owner-signed triage)

**RE-POPULATED 2026-09-09 evening.** The morning run below the line was measured in a
private per-worktree price store fetched that day, and its re-scorer captured the last
sensitivity arm for the two shared-harness families with sensitivity ladders; both are
fixed (REPRODUCIBILITY_GAP_ROOT_CAUSE_2026-09-09.md). The lines in this file are now the
evening re-run on the SHARED, REPAIRED store: the same 16 families, the same frozen specs,
every field re-measured. What moved: round_c, small_cap_disposition and eigenportfolio
drifts went from 0.0038 / 0.0077 / 0.0022 to 0.0 (they were the store); best_ideas 0.0008 ->
-0.0001. What did not move: asset_growth +0.0142 and pead_ear -0.0155 (not price-store
effects — their fundamentals/earnings inputs are the remaining suspects, unverified) and
dividend_payment_pressure +0.0489 (its gitignored payment calendar was rebuilt today,
after the 2026-09-06 production run; consistent with, not proven to be, the cause).
tax_loss_selling_turn_of_year, its small-cap twin and margin_credit are staged by the
script WITH an attribution warning and remain NOT PARKED on attribution grounds, exactly
as decided in the morning review (reversible; see the staged file's `skipped`).

---

- asset_growth/ag_low_ls_h126: persisted +0.2926 n=2928 | cut 2026-08-31 n_match=True | rerun +0.3068 drift +0.0142 | phi +0.031 LOW | pit_ok=True | ext 5 look 0 | asset_growth__ag_low_ls_h126__2026-09-09.json | 15s
- residual_momentum/rm_ff3_residual_neutral_ls_h21: persisted +0.2921 n=2929 | cut 2026-09-01 n_match=True | rerun +0.2920 drift -0.0001 | phi +0.018 LOW | pit_ok=True | ext 4 look 0 | residual_momentum__rm_ff3_residual_neutral_ls_h21__2026-09-09.json | 27s
- best_ideas_13f/bi_conviction_count_h63: persisted +0.6721 n=2890 | cut 2026-08-30 n_match=True | rerun +0.6729 drift +0.0008 | phi -0.001 LOW | pit_ok=True | ext 6 look 0 | best_ideas_13f__bi_conviction_count_h63__2026-09-09.json | 44s
- ivol: nothing to park (best ivol_resid_w21_hedged_h126 -0.114)
- buyback/nsi_l504_ls_h126: persisted +0.4496 n=2175 | cut 2026-08-30 n_match=True | rerun +0.4496 drift -0.0000 | phi -0.008 LOW | pit_ok=True | ext 6 look 0 | buyback__nsi_l504_ls_h126__2026-09-09.json | 186s
- bonds/bonds_curve_carry_l63_h126: persisted +0.3449 n=4877 | cut 2026-08-30 n_match=True | rerun +0.3449 drift -0.0000 | phi -0.023 LOW | pit_ok=True | ext 6 look 0 | bonds__bonds_curve_carry_l63_h126__2026-09-09.json | 22s
- fx: re-run FAILED RuntimeError: FRED_API_KEY is not configured — the FX carry signal cannot be built without the OECD 3-month interbank panel (see FRED_RATE_SERIES).
- commodities/cmd_momentum_l126_h126_inverse_vol: persisted +0.9048 n=2456 | cut 2026-08-30 n_match=True | rerun +0.9048 drift +0.0000 | phi -0.037 LOW | pit_ok=True | ext 6 look 0 | commodities__cmd_momentum_l126_h126_inverse_vol__2026-09-09.json | 15s
- vol_regime/vol_vxn_vix_h21_spy_ief: persisted +0.2302 n=4602 | cut 2026-08-30 n_match=True | rerun +0.2302 drift -0.0000 | phi -0.128 LOW | pit_ok=True | ext 6 look 0 | vol_regime__vol_vxn_vix_h21_spy_ief__2026-09-09.json | 5s
- dividend_month_premium: nothing to park (best dmp_one_after_yield_month -0.117)
- dividend_payment_pressure/divpay_raw_payment_top10: persisted +0.4030 n=2180 | cut 2026-09-06 n_match=True | rerun +0.4519 drift +0.0489 | phi -0.141 LOW | pit_ok=True | ext 1 look 0 | dividend_payment_pressure__divpay_raw_payment_top10__2026-09-09.json | 8s
- earnings_announcement_premium: nothing to park (best eap_b5_a1_ann_vol -0.233)
- pead_ear/pead_ear_wm1p1_h126_equal: persisted +0.1017 n=2909 | cut 2026-08-30 n_match=True | rerun +0.0862 drift -0.0155 | phi +0.006 LOW | pit_ok=True | ext 6 look 0 | pead_ear__pead_ear_wm1p1_h126_equal__2026-09-09.json | 295s
- insider_opportunistic/insider_opp_buy_h21_c2_equal: persisted +0.0703 n=2894 | cut 2026-08-30 n_match=True | rerun +0.0703 drift -0.0000 | phi -0.015 LOW | pit_ok=True | ext 6 look 0 | insider_opportunistic__insider_opp_buy_h21_c2_equal__2026-09-09.json | 407s
- index_removal: nothing to park (best index_removal_rebound_h126_equal -0.012)
- liquidity_shock_delta_illiq: nothing to park (best illiq_shock_std_h63_ls -0.065)
- correlation_risk_premium/crp_realized_21d_h63: persisted +0.2587 n=4936 | cut 2026-08-30 n_match=True | rerun +0.2587 drift +0.0000 | phi -0.125 LOW | pit_ok=True | ext 6 look 0 | correlation_risk_premium__crp_realized_21d_h63__2026-09-09.json | 5s
- country_valmom: nothing to park (best cvm_ltr_5y_rank_weighted_h21 -0.100)
- tax_loss_selling_turn_of_year/tls_jun_placebo_signed_h21: persisted +0.5259 n=2932 | cut 2026-09-05 n_match=True | rerun +0.4939 drift -0.0320 | phi +0.058 LOW | pit_ok=False | ext 1 look 0 | tax_loss_selling_turn_of_year__tls_jun_placebo_signed_h21__2026-09-09.json | 430s
- small_cap_tax_loss_selling_turn_of_year/tls_jun_placebo_signed_h21: persisted +0.5343 n=1677 | cut 2026-09-05 n_match=True | rerun +0.5081 drift -0.0262 | phi +0.135 HIGH | pit_ok=True | ext 1 look 0 | small_cap_tax_loss_selling_turn_of_year__tls_jun_placebo_signed_h21__2026-09-09.json | 274s
- fx/fx_momentum_l63_h126_inverse_vol: persisted +0.1582 n=3843 | cut 2026-09-04 n_match=True | rerun +0.1582 drift +0.0000 | phi -0.062 LOW | pit_ok=True | ext 0 look 0 | fx__fx_momentum_l63_h126_inverse_vol__2026-09-09.json | 22s
- tax_loss_selling_turn_of_year/tls_dec_jul_dec_lossonly_h6: persisted +0.4965 n=2932 | cut 2026-09-05 n_match=True | rerun +0.4664 drift -0.0301 | phi +0.057 LOW | pit_ok=False | ext 1 look 0 | tax_loss_selling_turn_of_year__tls_dec_jul_dec_lossonly_h6__2026-09-09.json | 384s
- small_cap_tax_loss_selling_turn_of_year/tls_dec_full_year_lossonly_h21: persisted +0.4152 n=1677 | cut 2026-09-05 n_match=True | rerun +0.3568 drift -0.0585 | phi -0.036 LOW | pit_ok=True | ext 1 look 0 | small_cap_tax_loss_selling_turn_of_year__tls_dec_full_year_lossonly_h21__2026-09-09.json | 219s
- small_cap_disposition/sc600_cgo_ls_decile_l504_h252: persisted +0.4541 n=1672 | cut 2026-08-30 n_match=True | rerun +0.4618 drift +0.0077 | phi +0.044 LOW | pit_ok=True | ext 6 look 0 | small_cap_disposition__sc600_cgo_ls_decile_l504_h252__2026-09-09.json | 58s
- small_cap_ivol: nothing to park (best sc600_ivol_resid_w21_hedged_h252 -0.416)
- same_calendar_month_seasonality: nothing to park (best seasonality_other_month_placebo_20y_ls +0.234)
- rebalancing_pressure/rebal_threshold_scaled_h1: persisted +0.5658 n=5810 | cut 2026-09-05 n_match=True | rerun +0.5658 drift -0.0000 | phi -0.138 LOW | pit_ok=True | ext 1 look 0 | rebalancing_pressure__rebal_threshold_scaled_h1__2026-09-09.json | 21s
- margin_credit/md__faithful__insample__meanvar: persisted +0.8559 n=194 | cut 2026-09-06 n_match=True | rerun +0.8559 drift +0.0000 | phi -0.129 LOW | pit_ok=True | ext 0 look 0 | margin_credit__md__faithful__insample__meanvar__2026-09-09.json | 1s
- ipo_lockup_expiration: nothing to park (best lockup|w_m5_p1|spy|vc -0.242)
- jump_drift: nothing to park (best jump_rev_w63_a010_h20 -0.205)
- eigenportfolio_statarb/eig_m1_c252_wide: persisted +0.0921 n=2886 | cut 2026-09-04 n_match=True | rerun +0.0943 drift +0.0022 | phi +0.115 HIGH | pit_ok=True | ext 0 look 0 | eigenportfolio_statarb__eig_m1_c252_wide__2026-09-09.json | 53s
- round_c/lps_intraday_l252_h63: persisted +0.2763 n=2927 | cut 2026-08-30 n_match=True | rerun +0.2725 drift -0.0038 | phi +0.022 LOW | pit_ok=True | ext 6 look 0 | round_c__lps_intraday_l252_h63__2026-09-09.json | 71s
- patterns_d2: nothing to park (best d2_reversal_long_universe_hedged_l504 -0.073)

staged 19 entries; skipped 20. Staged file: dormant_pool_manifest.staged.json
- small_cap_tax_loss_selling_turn_of_year/tls_dec_full_year_lossonly_h21: persisted +0.4152 n=1677 | cut 2026-09-05 n_match=True | rerun +0.3568 drift -0.0585 | phi -0.036 LOW | pit_ok=False | ext 1 look 0 | small_cap_tax_loss_selling_turn_of_year__tls_dec_full_year_lossonly_h21__2026-09-09.json | 225s
- margin_credit/md__faithful__recursive__meanvar: persisted +0.4626 n=51 | cut 2026-09-06 n_match=True | rerun +0.4626 drift +0.0000 | phi -0.102 LOW | pit_ok=True | ext 0 look 0 | margin_credit__md__faithful__recursive__meanvar__2026-09-09.json | 1s

staged 19 entries; skipped 20. Staged file: dormant_pool_manifest.staged.json
- asset_growth/ag_low_ls_h126: persisted +0.2926 n=2928 | cut 2026-08-31 n_match=True | rerun +0.3068 drift +0.0142 | phi +0.031 LOW | pit_ok=True | ext 5 look 0 | asset_growth__ag_low_ls_h126__2026-09-09.json | 607s
- residual_momentum/rm_ff3_residual_neutral_ls_h21: persisted +0.2921 n=2929 | cut 2026-09-01 n_match=True | rerun +0.2920 drift -0.0001 | phi +0.018 LOW | pit_ok=True | ext 4 look 0 | residual_momentum__rm_ff3_residual_neutral_ls_h21__2026-09-09.json | 14s
- best_ideas_13f/bi_conviction_count_h63: persisted +0.6721 n=2890 | cut 2026-08-30 n_match=True | rerun +0.6721 drift -0.0001 | phi -0.000 LOW | pit_ok=True | ext 6 look 0 | best_ideas_13f__bi_conviction_count_h63__2026-09-09.json | 15s
- ivol: nothing to park (best candidate spec ivol_resid_w21_hedged_h126 net Sharpe -0.1137 is not positive)
- buyback/nsi_l504_ls_h126: persisted +0.4496 n=2175 | cut 2026-08-30 n_match=True | rerun +0.4496 drift +0.0000 | phi -0.008 LOW | pit_ok=True | ext 6 look 0 | buyback__nsi_l504_ls_h126__2026-09-09.json | 201s
- bonds/bonds_curve_carry_l63_h126: persisted +0.3449 n=4877 | cut 2026-08-30 n_match=True | rerun +0.3449 drift -0.0000 | phi -0.023 LOW | pit_ok=True | ext 6 look 0 | bonds__bonds_curve_carry_l63_h126__2026-09-09.json | 21s
- fx/fx_momentum_l63_h126_inverse_vol: persisted +0.1582 n=3843 | cut 2026-09-04 n_match=True | rerun +0.1582 drift +0.0000 | phi -0.062 LOW | pit_ok=True | ext 0 look 0 | fx__fx_momentum_l63_h126_inverse_vol__2026-09-09.json | 23s
- commodities/cmd_momentum_l126_h126_inverse_vol: persisted +0.9048 n=2456 | cut 2026-08-30 n_match=True | rerun +0.9048 drift +0.0000 | phi -0.037 LOW | pit_ok=True | ext 5 look 0 | commodities__cmd_momentum_l126_h126_inverse_vol__2026-09-09.json | 16s
- vol_regime/vol_vxn_vix_h21_spy_ief: persisted +0.2302 n=4602 | cut 2026-08-30 n_match=True | rerun +0.2302 drift -0.0000 | phi -0.128 LOW | pit_ok=True | ext 6 look 0 | vol_regime__vol_vxn_vix_h21_spy_ief__2026-09-09.json | 3s
- dividend_month_premium: nothing to park (best candidate spec dmp_one_after_yield_month net Sharpe -0.1171 is not positive)
- dividend_payment_pressure: pattern divpay_raw_payment_top10 not captured; captured []
- earnings_announcement_premium: nothing to park (best candidate spec eap_b5_a1_ann_vol net Sharpe -0.2331 is not positive)
- pead_ear/pead_ear_wm1p1_h126_equal: persisted +0.1017 n=2909 | cut 2026-08-30 n_match=True | rerun +0.0862 drift -0.0155 | phi +0.006 LOW | pit_ok=True | ext 6 look 0 | pead_ear__pead_ear_wm1p1_h126_equal__2026-09-09.json | 302s
- insider_opportunistic/insider_opp_buy_h21_c2_equal: persisted +0.0703 n=2894 | cut 2026-08-30 n_match=True | rerun +0.0703 drift -0.0000 | phi -0.015 LOW | pit_ok=True | ext 6 look 0 | insider_opportunistic__insider_opp_buy_h21_c2_equal__2026-09-09.json | 357s
- index_removal: nothing to park (best candidate spec index_removal_rebound_h126_equal net Sharpe -0.0122 is not positive)
- liquidity_shock_delta_illiq: nothing to park (best candidate spec illiq_shock_std_h63_ls net Sharpe -0.0648 is not positive)
- correlation_risk_premium/crp_realized_21d_h63: persisted +0.2587 n=4936 | cut 2026-08-30 n_match=True | rerun +0.2587 drift +0.0000 | phi -0.125 LOW | pit_ok=True | ext 6 look 0 | correlation_risk_premium__crp_realized_21d_h63__2026-09-09.json | 5s
- country_valmom: nothing to park (best candidate spec cvm_ltr_5y_rank_weighted_h21 net Sharpe -0.0999 is not positive)
- tax_loss_selling_turn_of_year/tls_dec_jul_dec_lossonly_h6: persisted +0.4965 n=2932 | cut 2026-09-05 n_match=True | rerun +0.4966 drift +0.0000 | phi +0.063 LOW | pit_ok=True | ext 1 look 0 | tax_loss_selling_turn_of_year__tls_dec_jul_dec_lossonly_h6__2026-09-09.json | 392s
- small_cap_tax_loss_selling_turn_of_year/tls_dec_full_year_lossonly_h21: persisted +0.4152 n=1677 | cut 2026-09-05 n_match=True | rerun +0.4152 drift -0.0000 | phi -0.041 LOW | pit_ok=True | ext 1 look 0 | small_cap_tax_loss_selling_turn_of_year__tls_dec_full_year_lossonly_h21__2026-09-09.json | 277s
- small_cap_disposition/sc600_cgo_ls_decile_l504_h252: persisted +0.4541 n=1672 | cut 2026-08-30 n_match=True | rerun +0.4541 drift +0.0000 | phi +0.045 LOW | pit_ok=True | ext 6 look 0 | small_cap_disposition__sc600_cgo_ls_decile_l504_h252__2026-09-09.json | 9s
- small_cap_ivol: nothing to park (best candidate spec sc600_ivol_resid_w21_hedged_h252 net Sharpe -0.4157 is not positive)
- same_calendar_month_seasonality: nothing to park (best candidate spec seasonality_same_month_20y_lh net Sharpe -0.0533 is not positive; its control/placebo seasonality_other_month_placebo_20y_ls scores +0.2337, ABOVE every candidate spec - evidence against the family, not for it)
- rebalancing_pressure/rebal_threshold_scaled_h1: persisted +0.5658 n=5810 | cut 2026-09-05 n_match=True | rerun +0.5658 drift -0.0000 | phi -0.138 LOW | pit_ok=True | ext 1 look 0 | rebalancing_pressure__rebal_threshold_scaled_h1__2026-09-09.json | 20s
- margin_credit/md__faithful__recursive__meanvar: persisted +0.4626 n=51 | cut 2026-09-06 n_match=True | rerun +0.4626 drift +0.0000 | phi -0.102 LOW | pit_ok=True | ext 0 look 0 | margin_credit__md__faithful__recursive__meanvar__2026-09-09.json | 1s
- ipo_lockup_expiration: nothing to park (best candidate spec lockup|w_m5_p1|spy|vc net Sharpe -0.2424 is not positive)
- jump_drift: nothing to park (best candidate spec jump_rev_w63_a010_h20 net Sharpe -0.2049 is not positive)
- eigenportfolio_statarb/eig_m1_c252_wide: persisted +0.0921 n=2886 | cut 2026-09-04 n_match=True | rerun +0.0921 drift +0.0000 | phi +0.113 HIGH | pit_ok=True | ext 0 look 0 | eigenportfolio_statarb__eig_m1_c252_wide__2026-09-09.json | 54s
- round_c/lps_intraday_l252_h63: persisted +0.2763 n=2927 | cut 2026-08-30 n_match=True | rerun +0.2763 drift +0.0000 | phi +0.022 LOW | pit_ok=True | ext 6 look 0 | round_c__lps_intraday_l252_h63__2026-09-09.json | 32s
- patterns_d2: nothing to park (best candidate spec d2_reversal_long_universe_hedged_l504 net Sharpe -0.0726 is not positive)

staged 18 entries; skipped 21. Staged file: dormant_pool_manifest.staged.json
- dividend_payment_pressure/divpay_raw_payment_top10: persisted +0.4030 n=2180 | cut 2026-09-06 n_match=True | rerun +0.4519 drift +0.0489 | phi -0.141 LOW | pit_ok=True | ext 1 look 0 | dividend_payment_pressure__divpay_raw_payment_top10__2026-09-09.json | 9s

staged 19 entries; skipped 20. Staged file: dormant_pool_manifest.staged.json
