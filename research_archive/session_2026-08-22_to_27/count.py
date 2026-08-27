import sys, json, warnings
sys.path.insert(0,'/Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend')
warnings.filterwarnings('ignore')
from datetime import date, timedelta
from app.services.research_lab.sp500_membership_history import _EVENTS
import yfinance as yf, pandas as pd

KNOWN_RENAME = {('META','FB'),('ELV','ANTM'),('COR','ABC'),('RVTY','PKI'),('GEN','NLOK'),('WTW','WLTW'),('EG','RE'),('DOC','PEAK'),('CPAY','FLT'),('BALL','BLL'),('PSKY','PARA'),('MRSH','MMC'),('BNY','BK'),('ECHO','SATS'),('RTX','UTX'),('HWM','ARNC'),('VTRS','MYL'),('TFC','BBT'),('LHX','HRS'),('GL','TMK'),('BKR','BHGE'),('J','JEC'),('LIN','PX'),('FI','FISV'),('FISV','FI'),('DAY','CDAY'),('KHC','KRFT'),('SW','WRK'),('TT','XEC'),('CTRA','COG'),('WBD','DISCA'),('WBD','DISCK'),('LUMN','CTL'),('PARA','VIAC'),('VIAC','CBS'),('VIAC','VIAB'),('AMCR','MAT'),('BALL','BLL')}
removals=[]
for d,a,r in _EVENTS:
    for t in r:
        rename = any((x,t) in KNOWN_RENAME for x in a)
        removals.append({'ticker':t,'eff':d.isoformat(),'rename':rename})
print('total removal records', len(removals))
print('rename artifacts', sum(1 for x in removals if x['rename']))
cand=[x for x in removals if not x['rename']]
# only those with >=180 calendar days after eff within data coverage AND after 2015
cand=[x for x in cand if date.fromisoformat(x['eff']) <= date(2026,2,1)]
print('non-rename removals with >=~6mo of post-event runway', len(cand))
json.dump(cand, open('/private/tmp/claude-501/-Users-choonhakunjaroonwatthana-Desktop-aladdin2/be436747-4a23-4713-9fbf-e7e19fc0ad51/scratchpad/cand.json','w'))
