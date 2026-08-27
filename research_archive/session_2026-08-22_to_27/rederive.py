from app.services.research_lab.sp500_membership_history import vendored_events
ev = vendored_events()
adds = sum(len(a) for _,a,_ in ev); rems = sum(len(r) for _,_,r in ev)
print("dates",len(ev),"adds",adds,"removals",rems)
print("range", ev[0][0], ev[-1][0])
# check tuple shape / announcement field
print("tuple len", len(ev[0]), "fields", ev[0])
