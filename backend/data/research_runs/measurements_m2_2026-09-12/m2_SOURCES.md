# M2 sources — every primary document quoted, with SHA-256

Fetched 2026-09-12 with the SEC user agent `aladdin2 research autoa0792@gmail.com`, at or under
~7 requests/second.  Every hash is of the RAW bytes as fetched, so it can be checked against
EDGAR or the eCFR directly; the `.txt` files in this folder are extracts (title block plus the
verbatim sentences quoted), not the whole document.

The full census carries a hash for every one of the 348 offer documents in `m2_offers.csv`
(column `doc_sha256`) — the table below covers only the documents quoted in `M2_RESULT.md`.

## A. Law and literature

| file | sha256 | source | what it shows |
|---|---|---|---|
| `ecfr_240.13e-4.html` / `.txt` | `82e2e6a348513c78445ecbc6edb2bd1ba1456d7692bd95e980251a367773dfff` | eCFR, 17 CFR 240.13e-4, current text, https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-17?chapter=II&part=240&section=240.13e-4 | The odd-lot carve-out IS in the rule, at 240.13e-4(f)(3)(i), and the word "odd" appears zero times in the section — which is why the 2026-09-12 review's string search for "odd" concluded the regulatory basis was unverified. Verbatim: "Provided, however, That this provision shall not prohibit the issuer or affiliate making the issuer tender offer from: ( i ) Accepting all securities tendered by persons who own, beneficially or of record, an aggregate of not more than a specified number which is less than one hundred shares of such security and who tender all their securities, before prorating securities tendered by others". Note the wording is PERMISSIVE ("shall not prohibit"), not mandatory. |
| `kadapakkam_zhang_yildirim_2021_scholarsmine.html` | `f7f9359f552164f1971e30080707642ad0ea06fa48713e09760298cbccf60efc` | Kadapakkam, Zhang & Yildirim, *A Reexamination of the Tendering Profit Anomaly*, Review of Quantitative Finance and Accounting 56(4) 2021, https://scholarsmine.mst.edu/bio_inftec_facwork/359/ | Abstract, read verbatim: "we reexamine this strategy in recent years (2000–2015) and find that abnormal profits from tendering have disappeared… we find abnormal tendering profits of around 0.5%. However, these profits are no longer significant after adjustments for transaction costs." Re-fetched and re-hashed independently of the 2026-09-12 review; the page hash differs from the one recorded there (`afbad96f…`), the abstract text does not. |

## B. Offer documents — the clause, the terms, the traps

| extract file | sha256 of the raw document | EDGAR URL | what it shows |
|---|---|---|---|
| `trinet_group_inc_2022-02-17.txt` | `75ca59a0b9b591c9562a44c6d50123ffaf613e13254116bd914ea11847c31191` | https://www.sec.gov/Archives/edgar/data/937098/000110465922024466/tm226423d1_exh-a1i.htm | listed Dutch auction that grants odd-lot priority; the +10.81% premium row and the document's own reference price ($81.22) |
| `mgm_resorts_international_2020-02-13.txt` | `032b30eff93b08d7102d7ca4f9e0b18516a0d4738e0c5d7ff517242b5712ce66` | https://www.sec.gov/Archives/edgar/data/789570/000119312520034386/d849958dex99a1a.htm | listed Dutch auction, odd-lot priority; a NEGATIVE premium (range midpoint $31.50 vs the document's $33.66) |
| `virtus_total_return_fund_inc_2024-04-02.txt` | `a6d7ba719cf98a354f0aa4fcccb43ac170c41a686e4e5a6fdb15eb12bb2b4774` | https://www.sec.gov/Archives/edgar/data/836412/000119312524084792/d823267dex99a1i.htm | closed-end fund that EXPLICITLY DENIES odd-lot priority - the phrase is present, the provision is not |
| `japan_smaller_capitalization_fund_inc_2026-06-01.txt` | `b15967ce4968df871833c66610812c8465e54860df027b6339d13f6b2da121a6` | https://www.sec.gov/Archives/edgar/data/859796/000114036126023437/ny20074859x2_exa1i.htm | second explicit denial, 2026, showing the denial is not a one-off |
| `cummins_inc_2024-02-14.txt` | `df924fd4f92560a9ef3d23c2c0ebec349d467a2e40ecb55562418fd35821b3eb` | https://www.sec.gov/Archives/edgar/data/26172/000110465924034360/tm245866-6_sctoia.htm | split-off exchange offer (Atmus) whose odd-lot holders are exempted from proration - a non-cash variant of the same provision |
| `wheeler_real_estate_investment_trust_inc_2020-12-23.txt` | `639e02ae2d74e825103fee4af114aa2c0f7ace0689d59c70bcb936319d17ddab` | https://www.sec.gov/Archives/edgar/data/1527541/000121390020044397/ea132086ex99a1i_wheeler.htm | the class trap: the offer is for the Series D PREFERRED ($17.35) while the ticker's common printed $2.75 |
| `imperial_oil_ltd_2022-05-06.txt` | `16c49d254b2d709c6c1cb0438fac3dd18c4e2ac4a4d904449533abebd537e9c8` | https://www.sec.gov/Archives/edgar/data/49938/000119312522143506/d228787dex99a1i.htm | the currency trap: a Canadian substantial issuer bid quoted against the TSX close in CAD |
| `priority_income_fund_inc_2019-03-15.txt` | `ef175666bd85600b712a7f6f40d004256672f264d0c7ac5342c57612c84a66b6` | https://www.sec.gov/Archives/edgar/data/1554625/000155462519000046/exhibit99a1b32019.htm | non-traded BDC quarterly repurchase with an odd-lot preference - the modal filer in this population, unreachable on an exchange |
| `rum_group_inc_2025-01-03.txt` | `d5dc82bbf686f946c67994850b49324f06e763eccd9662d17100f0e8235a75b6` | https://www.sec.gov/Archives/edgar/data/1830081/000121390025000757/sctoi_ex99a1arumble.htm | the lowest premium in the bet population: a fixed price of $7.50 against a $12.40 close |
| `optimum_communications_inc_2026-06-01.txt` | `ea2ab9180b732dc1da161a331b08b7b485063d5fda1139cfa2e7df1d26d53b2d` | https://www.sec.gov/Archives/edgar/data/1702780/000121390026063179/ea029202901ex99a1a.htm | the highest premium in the bet population: $2.50 against a $0.65 close |
| `covenant_logistics_group_inc_2021-08-09.txt` | `ef21a6e6cc36d055857292ff892adbd7e70e8c0bac44fdb77fa64adb026edb7e` | https://www.sec.gov/Archives/edgar/data/928658/000100888621000080/exhibit99a1i.htm | the free-feed disagreement: the document states $20.27, yfinance reported a 4-for-1 split and 40.54 |

## C. Final amendments — the provision actually operating

| extract file | sha256 of the raw document | EDGAR URL | what it shows |
|---|---|---|---|
| `cummins_inc_2024-02-14_FINAL.txt` | `8657e1c61dd23d50c332935e3eaf13a40f25b74d31723dad447292c7e4f73986` | https://www.sec.gov/Archives/edgar/data/26172/000110465924035612/tm245866-7_sctoia.htm | the provision ACTUALLY OPERATING: odd-lot shares accepted in full while everyone else was cut to the stated proration factor |
| `eli_lilly_co_2019-02-08_FINAL.txt` | `fd4b3464517fd5f37fd0dd3528853b94b66d91ab7e15572328c17250b02995b1` | https://www.sec.gov/Archives/edgar/data/59478/000110465919014488/a18-39904_73sctoia.htm | the provision ACTUALLY OPERATING: odd-lot shares accepted in full while everyone else was cut to the stated proration factor |
| `3m_co_2022-08-04_FINAL.txt` | `0fea94fac8f686bc48cec18072e6a1356ad1890065b2d5a45590192fa86d5d08` | https://www.sec.gov/Archives/edgar/data/66740/000114036122032385/ny20004937x37_sctoia.htm | the provision ACTUALLY OPERATING: odd-lot shares accepted in full while everyone else was cut to the stated proration factor |
| `johnson_johnson_2023-07-24_FINAL.txt` | `c6b6efb8ce619e810ac89d0cf2385f231c06d0f49f584583ba556f8b244af0da` | https://www.sec.gov/Archives/edgar/data/200406/000162828023030300/jjscto-ia4.htm | the provision ACTUALLY OPERATING: odd-lot shares accepted in full while everyone else was cut to the stated proration factor |
| `danaher_corp_de_2019-11-15_FINAL.txt` | `554de715d2bbcbbe71acc79f3b6e782ac75d1add23c41aeb95b89052e49c55a7` | https://www.sec.gov/Archives/edgar/data/313616/000119312519316822/d844056dsctoia.htm | the provision ACTUALLY OPERATING: odd-lot shares accepted in full while everyone else was cut to the stated proration factor |
| `lennar_corp_new_2025-10-10_FINAL.txt` | `8968aab418f1dadd9bf8732e653d7e500206fcdfaa3e8bb5d72d16ded5f089e9` | https://www.sec.gov/Archives/edgar/data/920760/000119312525300679/d876414dsctoia.htm | the provision ACTUALLY OPERATING: odd-lot shares accepted in full while everyone else was cut to the stated proration factor |
| `mckesson_corp_2020-02-10_FINAL.txt` | `a3b85de825ea787937dae5fce9d898476981a79cc2c77571b523f5c51c94ada7` | https://www.sec.gov/Archives/edgar/data/927653/000119312520070982/d880776dsctoia.htm | the provision ACTUALLY OPERATING: odd-lot shares accepted in full while everyone else was cut to the stated proration factor |
