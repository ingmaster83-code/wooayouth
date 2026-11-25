# -*- coding: utf-8 -*-
"""
우아청년정책 수집기 — 한국고용정보원 온통청년 청년정책 Open API (youthcenter.go.kr, data.go.kr 15143273 연결형)
GET https://www.youthcenter.go.kr/go/ythip/getPlcy?apiKeyNm=KEY&pageNum=N&pageSize=100&rtnType=json  → 전체 약 4천 건(40호출)
키: 환경변수 YOUTH_API_KEY → 로컬 ../_newdata/youthcenter.env (코드에 넣지 않는다). 온통청년 발급키는 유효기간 1년(2026-09-09~2027-09-09) — 만료 전 재신청.
저장: data/policies.json.gz (필요 필드만). 직전보다 건수가 30% 넘게 줄면 중단(일시 오류 방어).
사용: python scripts/fetch_data.py
"""
import gzip, json, os, re, sys, time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
KEEP = ["plcyNo", "plcyNm", "plcyKywdNm", "plcyExplnCn", "plcySprtCn", "plcyAplyMthdCn", "srngMthdCn", "sbmsnDcmntCn", "aplyUrlAddr", "refUrlAddr1", "refUrlAddr2", "addAplyQlfcCndCn", "etcMttrCn",
        "ptcpPrpTrgtCn", "aplyYmd", "aplyPrdSeCd", "bizPrdBgngYmd", "bizPrdEndYmd", "bizPrdEtcCn", "lclsfNm", "mclsfNm", "sprtTrgtMinAge", "sprtTrgtMaxAge", "sprtTrgtAgeLmtYn", "earnCndSeCd",
        "earnMinAmt", "earnMaxAmt", "earnEtcCn", "sprvsnInstCdNm", "operInstCdNm", "rgtrInstCdNm", "rgtrUpInstCdNm", "zipCd", "inqCnt", "frstRegDt", "lastMdfcnDt", "sprtSclCnt"]


def api_key():
    if os.environ.get("YOUTH_API_KEY"):
        return os.environ["YOUTH_API_KEY"].strip()
    for p in (ROOT / ".env", ROOT.parent / "_newdata" / "youthcenter.env"):
        if p.exists():
            m = re.search(r"^YOUTH_API_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip("\"'")
    sys.exit("환경변수 YOUTH_API_KEY 가 필요합니다.")


def main():
    key = api_key()
    out, page, tot = [], 1, 0
    s = requests.Session()
    while True:
        last = ""
        for attempt in range(6):
            try:
                j = s.get(URL, params=dict(apiKeyNm=key, pageNum=page, pageSize=100, rtnType="json"), timeout=90).json()
                if j.get("resultCode") != 200:
                    raise RuntimeError(str(j.get("resultMessage")))
                break
            except Exception as e:
                last = str(e)
                time.sleep(3 + 4 * attempt)
        else:
            sys.exit("API 실패 page %d: %s" % (page, last))
        r = j["result"]
        tot = int(r["pagging"]["totCount"])
        L = r["youthPolicyList"]
        out += [{k: (x.get(k) if x.get(k) is not None else "") for k in KEEP} for x in L]
        print(page, len(out), tot, flush=True)
        if len(out) >= tot or not L:
            break
        page += 1
        time.sleep(0.3)
    uniq = {x["plcyNo"]: x for x in out}
    rows = sorted(uniq.values(), key=lambda x: x["plcyNo"])
    p = DATA / "policies.json.gz"
    if p.exists():
        prev = len(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
        if prev > 1000 and len(rows) < prev * 0.7:
            sys.exit("건수가 직전(%d)보다 크게 줄어(%d) 중단" % (prev, len(rows)))
    with gzip.GzipFile(p, "wb", compresslevel=9, mtime=0) as f:
        f.write(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print("완료:", len(rows))


if __name__ == "__main__":
    main()
