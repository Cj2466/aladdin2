"""Extract the Z.1 corporate-equities (instrument 30641) sector panel from the
Federal Reserve's free FRB_Z1_xml.zip bulk file into a compact CSV.

Source: https://www.federalreserve.gov/releases/z1/data/FRB_Z1_xml.zip
Vintage used here: Prepared 2026-06-10, "Release Date: June 11, 2026, 2026:Q1".

Z.1 series-name grammar (from Z1_Z1.xsd code lists):
    <PREFIX><SECTOR(2)><INSTRUMENT(5)><SUFFIX(2)>.<FREQ>
  PREFIX  LM = level, market value, NSA   FL = level, NSA
          FU = transactions NSA           FA = transactions SAAR
  INSTRUMENT 30641 = corporate equities
  SUFFIX last digit 5 = ASSET (holder), 3 = LIABILITY (issuer)

This script does no economics; it only reshapes the Fed's own XML.
"""
import csv
import sys
import xml.etree.ElementTree as ET

NS_KF = "{http://www.federalreserve.gov/structure/compact/Z1_Z1}Series"
NS_OBS = "{http://www.federalreserve.gov/structure/compact/common}Obs"
NS_ANN_T = "{http://www.SDMX.org/resources/SDMXML/schemas/v1_0/common}AnnotationType"
NS_ANN_X = "{http://www.SDMX.org/resources/SDMXML/schemas/v1_0/common}AnnotationText"
INSTRUMENT = "30641"


def main(xml_path: str, out_obs: str, out_meta: str) -> None:
    obs_rows, meta_rows = [], []
    for event, elem in ET.iterparse(xml_path, events=("end",)):
        # NOTE: only Series elements are cleared. Clearing every element at its
        # own "end" event would wipe the <frb:Obs> children before the parent
        # Series end event ever fires (found the hard way: 291 series, 0 obs).
        if elem.tag != NS_KF:
            continue
        if elem.get("SERIES_INSTRUMENT") != INSTRUMENT:
            elem.clear()
            continue
        name = elem.get("SERIES_NAME", "")
        if not name.endswith(".Q"):
            elem.clear()
            continue
        desc = ""
        for ann in elem.iter():
            if ann.tag == NS_ANN_X and not desc:
                desc = (ann.text or "").strip()
        meta_rows.append(
            {
                "series_name": name,
                "prefix": elem.get("SERIES_PREFIX", ""),
                "sector": elem.get("SERIES_SECTOR", ""),
                "unit_mult": elem.get("UNIT_MULT", ""),
                "description": desc,
            }
        )
        for obs in elem.iter(NS_OBS):
            val = obs.get("OBS_VALUE")
            if val in (None, "", "ND"):
                continue
            obs_rows.append(
                {
                    "series_name": name,
                    "period": obs.get("TIME_PERIOD"),
                    "value": val,
                    "status": obs.get("OBS_STATUS", ""),
                }
            )
        elem.clear()

    with open(out_obs, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["series_name", "period", "value", "status"])
        w.writeheader()
        w.writerows(obs_rows)
    with open(out_meta, "w", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["series_name", "prefix", "sector", "unit_mult", "description"]
        )
        w.writeheader()
        w.writerows(meta_rows)
    print(f"series={len(meta_rows)} observations={len(obs_rows)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
