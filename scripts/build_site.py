# -*- coding: utf-8 -*-
"""우아청년정책 정적 사이트 생성기.
입력: data/policies.json.gz (온통청년 청년정책 API 전체)
대상: 신청기간이 아직 안 끝난 정책 + 상시 신청 정책(마감된 것·기간 지난 것은 제외)
출력: _site/ (정책 상세, 분야·지역·나이·키워드 허브, 마감 임박·상시, 검색 인덱스, sitemap). 매일 새로 받아 다시 만든다.
"""
import collections, datetime as dt, gzip, json, os, re, shutil, sys
from datetime import timedelta, timezone

from common import *  # noqa

sys.stdout.reconfigure(encoding="utf-8")
DATA = pathlib.Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else ROOT / "data"
TODAY = (dt.datetime.now(timezone.utc) + timedelta(hours=9)).date()

CATS = collections.OrderedDict([("job", "일자리"), ("housing", "주거"), ("edu", "교육"), ("welfare", "복지·문화"), ("civic", "참여·권리")])
CATMAP = {"일자리": "job", "주거": "housing", "교육･직업훈련": "edu", "교육": "edu", "금융･복지･문화": "welfare", "복지문화": "welfare", "참여･기반": "civic", "참여권리": "civic"}
CAT_DESC = {"job": "취업·창업·재직자 지원", "housing": "전월세·주택·기숙사 지원", "edu": "교육비·직업훈련·역량강화", "welfare": "금융·복지·문화·건강", "civic": "청년참여·권리·국제교류"}
PREFIX = {"11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "전남광주", "12": "전남광주", "46": "전남광주", "30": "대전", "31": "울산", "36": "세종", "41": "경기", "42": "강원", "51": "강원",
          "43": "충북", "44": "충남", "45": "전북", "52": "전북", "47": "경북", "48": "경남", "50": "제주"}
SIDOS = ["서울", "부산", "대구", "인천", "전남광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "경북", "경남", "제주"]
SIDO_FULL = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "전남광주", "전라남도": "전남광주", "전남광주통합특별시": "전남광주", "대전광역시": "대전",
             "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북",
             "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}


def clean(s):
    s = (s or "").replace("\\N", "\n").replace("\r", "")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def one(s):
    return re.sub(r"\s+", " ", clean(s)).strip()


def cut(s, n):
    return s if len(s) <= n else s[:n].rstrip(" ,/·") + "…"


def pdate(s):
    return dt.datetime.strptime(s, "%Y%m%d").date()


def fmt(d):
    return "%d.%02d.%02d" % (d.year, d.month, d.day)


def ranges(s):
    ds = re.findall(r"\d{8}", s or "")
    out = []
    for i in range(0, len(ds) - 1, 2):
        try:
            out.append((pdate(ds[i]), pdate(ds[i + 1])))
        except ValueError:
            pass
    return out


def codes(x):
    return [c for c in (x.get("zipCd") or "").split(",") if c.strip()]


def load():
    rows = json.loads(gzip.open(DATA / "policies.json.gz", "rt", encoding="utf-8").read())
    # 시군구 이름표: 코드 1개짜리 정책의 운영기관 이름("강원특별자치도 원주시 …")에서 다수결
    votes = collections.defaultdict(collections.Counter)
    for x in rows:
        cs = codes(x)
        if len(cs) == 1:
            for f in ("sprvsnInstCdNm", "rgtrInstCdNm", "operInstCdNm"):
                t = (x.get(f) or "").split()
                if len(t) >= 2 and t[0] in SIDO_FULL and re.search(r"(시|군|구)$", t[1]) and not re.search(r"(청|부|처)$", t[1]):
                    votes[cs[0]][t[1]] += 1
                    break
    sgg_name = {c: v.most_common(1)[0][0] for c, v in votes.items() if v.most_common(1)[0][1] >= 2}
    ps = []
    for x in rows:
        pc = x.get("aplyPrdSeCd")
        if pc == "0057003":
            continue
        rg = ranges(x.get("aplyYmd"))
        if pc == "0057002" or not rg:
            if pc != "0057002":
                continue
            status, start, end = "상시", None, None
        else:
            cur = [r for r in rg if r[1] >= TODAY]
            if not cur:
                continue
            start, end = cur[0]
            status = "진행" if start <= TODAY else "예정"
        cs = codes(x)
        nat = len(cs) >= 200
        sidos = []
        for c in cs:
            sd = PREFIX.get(c[:2])
            if sd and sd not in sidos:
                sidos.append(sd)
        sgg = ""
        sggs = [sgg_name[c] for c in cs if c in sgg_name]
        if len(cs) == 1 and sggs and sidos:
            sgg = sggs[0]
        lc = (x.get("lclsfNm") or "").split(",")[0].strip()
        cat = CATS.get(CATMAP.get(lc, ""), "")
        if not cat:
            continue
        name = one(x["plcyNm"]).replace("(접수 마감)", "").strip()
        if not name:
            continue
        mn, mx = int(x.get("sprtTrgtMinAge") or 0), int(x.get("sprtTrgtMaxAge") or 0)
        tags = [k.strip() for k in (x.get("plcyKywdNm") or "").split(",") if k.strip()]
        inc = ""
        ec = x.get("earnCndSeCd")
        if ec == "0043002":
            a, b = int(x.get("earnMinAmt") or 0), int(x.get("earnMaxAmt") or 0)
            inc = "연소득 %s" % (("%s~%s만원" % ("{:,}".format(a), "{:,}".format(b))) if a and b else ("%s만원 이하" % "{:,}".format(b) if b else "%s만원 이상" % "{:,}".format(a)))
        elif ec == "0043003":
            inc = one(x.get("earnEtcCn"))
            inc = "" if inc in ("", "-") else inc
        elif ec == "0043001":
            inc = "소득 조건 없음"
        ps.append(dict(id=x["plcyNo"], name=name, cat=cat, mid=one(x.get("mclsfNm")).split(",")[0].strip(), sidos=[] if nat else sidos, nat=nat or not sidos, sgg=sgg, sggcode=cs[0] if len(cs) == 1 else "",
                       agency=one(x.get("sprvsnInstCdNm")) or one(x.get("operInstCdNm")) or one(x.get("rgtrInstCdNm")), mn=mn, mx=mx, inc=inc, status=status, start=start, end=end, tags=tags,
                       expl=clean(x.get("plcyExplnCn")), sup=clean(x.get("plcySprtCn")), how=clean(x.get("plcyAplyMthdCn")), srng=clean(x.get("srngMthdCn")), docs=clean(x.get("sbmsnDcmntCn")),
                       qual=clean(x.get("addAplyQlfcCndCn")), etc=clean(x.get("etcMttrCn")), prop=clean(x.get("ptcpPrpTrgtCn")), url=(x.get("aplyUrlAddr") or "").strip(), ref=(x.get("refUrlAddr1") or "").strip(),
                       ref2=(x.get("refUrlAddr2") or "").strip(), bp=(one(x.get("bizPrdEtcCn")) or ""), inq=int(x.get("inqCnt") or 0), mod=(x.get("lastMdfcnDt") or "")[:10]))
    return ps, len(rows)


def age_txt(p):
    if p["mn"] and p["mx"]:
        return "만 %d~%d세" % (p["mn"], p["mx"])
    if p["mn"]:
        return "만 %d세 이상" % p["mn"]
    if p["mx"]:
        return "만 %d세 이하" % p["mx"]
    return "연령 제한 없음"


def when(p):
    if p["status"] == "상시":
        return "상시 신청"
    s = "%s ~ %s" % (fmt(p["start"]), fmt(p["end"]))
    return s


def dday(p):
    if p["status"] == "상시":
        return ""
    if p["status"] == "예정":
        return "D-%d 시작" % (p["start"] - TODAY).days
    d = (p["end"] - TODAY).days
    return "오늘 마감" if d == 0 else "D-%d" % d


def region_txt(p):
    if p["nat"]:
        return "전국"
    return " ".join(x for x in ((p["sidos"][0] if p["sidos"] else ""), p["sgg"]) if x) + ((" 외" if len(p["sidos"]) > 1 else ""))


def link(p):
    return '<a href="/policy/%s/">%s</a>' % (p["id"], esc(cut(p["name"], 60)))


def ptable(L, cap=100):
    L = L[:cap]
    rows = []
    for p in L:
        dd = dday(p)
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s%s</td></tr>" % (link(p), esc(p["cat"]), esc(region_txt(p)), esc(when(p)), (' <span class="badge hot">%s</span>' % dd) if dd and p["status"] == "진행" and (p["end"] - TODAY).days <= 14 else ""))
    return '<div class="tbl-wrap"><table class="tbl"><tr><th>정책</th><th>분야</th><th>지역</th><th>신청 기간</th></tr>%s</table></div>' % "".join(rows)


def stat(L):
    n = len(L)
    al = sum(1 for p in L if p["status"] == "상시")
    soon = sum(1 for p in L if p["status"] == "진행" and (p["end"] - TODAY).days <= 14)
    return '<p class="lead">%s 기준 신청할 수 있는 청년정책 <b>%d개</b>입니다(상시 신청 %d개, 2주 안에 마감 %d개).</p>' % (fmt(TODAY), n, al, soon)


def hub(path, h1, sub, L, extra="", cap=100, title=None, desc=None, crumbs=None, prio="0.7", faq=None, sort=True):
    if sort:
        L = sorted(L, key=lambda p: (p["status"] == "상시", p["end"] or dt.date(2100, 1, 1), p["id"]))
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(h1), esc(sub)), stat(L), ad(), extra, '<h2 class="group-title">정책 목록</h2>', ptable(L, cap)]
    if len(L) > cap:
        body.append('<p class="note">정책이 많아 %d개만 표시했습니다. 분야·지역별 페이지에서 좁혀 보세요.</p>' % cap)
    write(path, layout(path, title or h1, desc or sub, "\n".join(b for b in body if b), faq, crumbs or [("홈", "/")], coupang=True), prio)


def sect(title, text):
    if not text or text in ("-",):
        return ""
    return '<h2 class="group-title">%s</h2><div class="lead pre">%s</div>' % (esc(title), esc(cut(text, 2500)))


def page_policy(p, by_sido, by_c, hubs_ok):
    lead = "<b>%s</b>은(는) %s이(가) 운영하는 %s 분야 청년정책입니다. 대상은 %s이고 신청은 %s입니다." % (esc(p["name"]), esc(p["agency"] or "운영기관"), esc(p["cat"]), esc(age_txt(p)), esc(when(p)))
    info = [("분야", "%s%s" % (p["cat"], (" · " + p["mid"]) if p["mid"] else "")), ("대상 연령", age_txt(p)), ("소득 조건", p["inc"]), ("신청 기간", when(p) + ((" (%s)" % dday(p)) if dday(p) else "")), ("지역", region_txt(p)),
            ("운영기관", p["agency"]), ("사업 기간", p["bp"]), ("키워드", ", ".join(p["tags"]))]
    itbl = '<div class="tbl-wrap"><table class="tbl">%s</table></div>' % "".join("<tr><th>%s</th><td>%s</td></tr>" % (a, esc(b)) for a, b in info if b)
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(p["name"]), esc(" · ".join(x for x in (p["cat"], region_txt(p), age_txt(p)) if x))), '<p class="lead">%s</p>' % lead, ad(), itbl,
            sect("정책 소개", p["expl"]), sect("지원 내용", p["sup"]), sect("추가 신청 자격", p["qual"]), sect("신청 방법", p["how"]), sect("심사·선정 방법", p["srng"]), sect("제출 서류", p["docs"]), sect("기타 유의사항", p["etc"])]
    acts = []
    for u, label in ((p["url"], "📝 신청 페이지"), (p["ref"], "ℹ️ 정책 상세 안내"), (p["ref2"], "🔗 참고 링크")):
        if u.startswith("http") and not any(u == a for a, _ in [(x[0], x[1]) for x in []]):
            acts.append('<a class="btn" href="%s" rel="nofollow noopener" target="_blank">%s</a>' % (esc(u), label))
    if acts:
        body.append("<p>%s</p>" % " ".join(acts[:3]))
    body.append('<div class="note-box">정책 정보는 한국고용정보원 온통청년 Open API 기준이며 신청 기간·자격·지원 금액은 바뀔 수 있습니다. 신청 전에 운영기관 공고를 꼭 확인하세요. 마지막 수정일 %s.</div>' % esc(p["mod"] or "-"))
    sib = [o for o in by_c[p["cat"]] if o is not p and ((p["sidos"] and set(o["sidos"]) & set(p["sidos"])) or (not p["sidos"] and o["nat"]))][:6]
    if sib:
        body.append('<h2 class="group-title">비슷한 청년정책</h2>' + ptable(sib, 6))
    chips = ['<a class="chip" href="/category/%s/">%s 정책 전체</a>' % (next(k for k, v in CATS.items() if v == p["cat"]), esc(p["cat"]))]
    if p["sidos"] and p["sidos"][0] in by_sido:
        chips.append('<a class="chip" href="/region/%s/">%s 청년정책</a>' % (q(p["sidos"][0]), esc(p["sidos"][0])))
    for t in p["tags"][:3]:
        if ("kw", t) in hubs_ok:
            chips.append('<a class="chip" href="/keyword/%s/">%s</a>' % (q(t), esc(t)))
    body.append('<div class="chips">%s</div>' % "".join(chips))
    faq = [("%s은(는) 누가 신청할 수 있나요?" % p["name"], "%s이(가) 대상으로 등록돼 있습니다.%s%s 정확한 자격은 운영기관 공고를 확인하세요." % (age_txt(p), (" 소득 조건: %s." % p["inc"]) if p["inc"] else "", (" 추가 자격: %s" % cut(one(p["qual"]), 160)) if p["qual"] else "")),
           ("%s 신청 기간은 언제인가요?" % p["name"], ("상시 신청으로 등록돼 있습니다." if p["status"] == "상시" else "%s입니다(%s)." % (when(p), dday(p))))]
    if p["how"]:
        faq.append(("%s은(는) 어떻게 신청하나요?" % p["name"], cut(one(p["how"]), 300)))
    crumbs = [("홈", "/"), (p["cat"], "/category/%s/" % next(k for k, v in CATS.items() if v == p["cat"])), (cut(p["name"], 28), "/policy/%s/" % p["id"])]
    ld = [{"@context": "https://schema.org", "@type": "GovernmentService", "name": p["name"], "serviceType": p["cat"] + " 청년정책", "provider": {"@type": "GovernmentOrganization", "name": p["agency"] or "운영기관"},
           "description": cut(one(p["expl"] or p["sup"]), 200)}]
    title = "%s - 신청 대상·방법·기간 | %s청년정책" % (p["tname"], (p["sidos"][0] + " ") if p["sidos"] else "")
    desc = "%s: %s 대상, %s. %s" % (cut(p["name"], 40), age_txt(p), when(p), cut(one(p["expl"] or p["sup"]), 90))
    write("/policy/%s/" % p["id"], layout("/policy/%s/" % p["id"], title.replace(" | 청년정책", " | 우아청년정책"), desc, "\n".join(body), faq, crumbs, "article", ld, coupang=True), "0.6")


def build():
    ps, total = load()
    print("전체", total, "→ 신청 가능", len(ps))
    ps.sort(key=lambda p: (p["status"] == "상시", p["end"] or dt.date(2100, 1, 1), p["id"]))
    by_c, by_sido, by_sgg, by_kw = (collections.defaultdict(list) for _ in range(4))
    nat = []
    for p in ps:
        by_c[p["cat"]].append(p)
        for s in p["sidos"]:
            by_sido[s].append(p)
        if p["nat"]:
            nat.append(p)
        if p["sgg"] and p["sidos"]:
            by_sgg[(p["sidos"][0], p["sgg"])].append(p)
        for t in p["tags"]:
            by_kw[t].append(p)
    cnt = collections.Counter(p["name"] for p in ps)
    for p in ps:
        p["tname"] = cut(p["name"], 40) if cnt[p["name"]] == 1 else "%s (%s)" % (cut(p["name"], 24), cut(p["agency"] or region_txt(p), 16))
    cnt2 = collections.Counter(p["tname"] for p in ps)
    for p in ps:
        if cnt2[p["tname"]] > 1:
            p["tname"] += " " + p["id"][-4:]
    hubs_ok = {("kw", t) for t, L in by_kw.items() if len(L) >= 8} | {("sgg", s, g) for (s, g), L in by_sgg.items() if len(L) >= 3}
    OUT.mkdir(parents=True, exist_ok=True)
    for ch in OUT.iterdir():
        shutil.rmtree(ch) if ch.is_dir() else ch.unlink()
    for p in ps:
        page_policy(p, by_sido, by_c, hubs_ok)
    # 분야
    for slug, cat in CATS.items():
        L = by_c[cat]
        mids = collections.Counter(p["mid"] for p in L if p["mid"])
        sc = collections.Counter(s for p in L for s in p["sidos"])
        extra = '<h2 class="group-title">세부 분야</h2><div class="chips">%s</div>' % "".join('<span class="chip">%s <small>%d</small></span>' % (esc(m), n) for m, n in mids.most_common(8))
        extra += '<h2 class="group-title">지역별</h2><div class="chips">%s</div>' % "".join(
            ('<a class="chip" href="/category/%s/%s/">%s <small>%d</small></a>' % (slug, q(s), esc(s), sc[s])) if sc[s] >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(s), sc[s]) for s in SIDOS if sc[s])
        hub("/category/%s/" % slug, "%s 청년정책 %d개" % (cat, len(L)), CAT_DESC[slug], L, extra, 100, "%s 청년정책 신청 가능 %d개 - 지원금·대상·기간" % (cat, len(L)),
            "%s 분야 청년정책 %d개의 신청 대상, 기간, 지원 내용을 정리했습니다. 지역별로 좁혀 보세요." % (cat, len(L)), [("홈", "/"), ("분야별", "/category/"), (cat, "/category/%s/" % slug)], "0.8")
        for s in SIDOS:
            L2 = [p for p in L if s in p["sidos"]]
            if len(L2) >= 3:
                hub("/category/%s/%s/" % (slug, s), "%s %s 청년정책 %d개" % (s, cat, len(L2)), "%s 지역 %s 분야" % (s, cat), L2, "", 100, "%s %s 청년정책 %d개 - 신청 대상·기간" % (s, cat, len(L2)),
                    "%s의 %s 분야 청년정책 %d개를 신청 기간 순으로 정리했습니다." % (s, cat, len(L2)), [("홈", "/"), (cat, "/category/%s/" % slug), (s, "/category/%s/%s/" % (slug, s))], "0.6")
    cards = "".join('<a class="card" href="/category/%s/"><b>%s</b><span>%d개 · %s</span></a>' % (k, esc(v), len(by_c[v]), esc(CAT_DESC[k])) for k, v in CATS.items())
    write("/category/", layout("/category/", "분야별 청년정책", "일자리·주거·교육·복지문화·참여권리 분야별 청년정책", '<div class="page-head"><h1>분야별 청년정책</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("분야별", "/category/")]), "0.8")
    # 지역
    for s in SIDOS:
        L = by_sido[s]
        if not L:
            continue
        gc = collections.Counter(p["sgg"] for p in L if p["sgg"])
        extra = ""
        if gc:
            extra = '<h2 class="group-title">시군구별</h2><div class="chips">%s</div>' % "".join(
                ('<a class="chip" href="/region/%s/%s/">%s <small>%d</small></a>' % (q(s), q(g), esc(g), n)) if ("sgg", s, g) in hubs_ok else '<span class="chip">%s <small>%d</small></span>' % (esc(g), n) for g, n in gc.most_common(60))
        cc = collections.Counter(p["cat"] for p in L)
        extra += '<h2 class="group-title">분야별</h2><div class="chips">%s</div>' % "".join(
            ('<a class="chip" href="/category/%s/%s/">%s <small>%d</small></a>' % (k, q(s), esc(v), cc[v])) if cc[v] >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(v), cc[v]) for k, v in CATS.items() if cc[v])
        hub("/region/%s/" % s, "%s 청년정책 %d개 - 지원금·주거·일자리" % (s, len(L)), "%s 지역에서 신청할 수 있는 청년정책" % s, L, extra, 100, "%s 청년정책 %d개 - 신청 가능 지원금·주거·일자리" % (s, len(L)),
            "%s 청년이 신청할 수 있는 정책 %d개를 분야·신청 기간별로 정리했습니다. 청년 월세·교통비·취업 지원을 확인하세요." % (s, len(L)), [("홈", "/"), ("지역별", "/region/"), (s, "/region/%s/" % s)], "0.8")
    for (s, g), L in by_sgg.items():
        if ("sgg", s, g) in hubs_ok:
            hub("/region/%s/%s/" % (s, g), "%s %s 청년정책 %d개" % (s, g, len(L)), "%s %s에서 신청할 수 있는 청년정책" % (s, g), L, "", 100, "%s %s 청년정책 %d개 - 신청 대상·기간" % (s, g, len(L)),
                "%s %s 청년이 신청할 수 있는 정책 %d개를 정리했습니다." % (s, g, len(L)), [("홈", "/"), (s, "/region/%s/" % s), (g, "/region/%s/%s/" % (s, g))], "0.6")
    cards = "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d개</span></a>' % (q(s), esc(s), len(by_sido[s])) for s in SIDOS if by_sido[s])
    cards = '<a class="card" href="/nationwide/"><b>전국 대상</b><span>%d개</span></a>' % len(nat) + cards
    write("/region/", layout("/region/", "지역별 청년정책", "시도·시군구별 청년정책을 확인하세요.", '<div class="page-head"><h1>지역별 청년정책</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("지역별", "/region/")]), "0.8")
    hub("/nationwide/", "전국 청년이 신청할 수 있는 정책 %d개" % len(nat), "거주 지역과 관계없이 신청 가능한 정책", nat, "", 100, "전국 청년정책 %d개 - 지역 무관 신청 가능" % len(nat), "거주 지역과 관계없이 전국 청년이 신청할 수 있는 정책 %d개를 정리했습니다." % len(nat), [("홈", "/"), ("전국", "/nationwide/")], "0.8")
    # 나이
    for a in range(19, 40):
        L = [p for p in ps if (not p["mn"] or p["mn"] <= a) and (not p["mx"] or p["mx"] >= a)]
        L2 = [p for p in L if p["mn"] or p["mx"]]
        if len(L2) < 5:
            continue
        hub("/age/%d/" % a, "만 %d세 청년이 받을 수 있는 정책 %d개" % (a, len(L)), "연령 조건이 %d세를 포함하는 정책" % a, L, "", 100, "만 %d세 청년 지원 정책 %d개 - 신청 가능 목록" % (a, len(L)),
            "만 %d세가 신청할 수 있는 청년정책 %d개를 신청 기간 순으로 정리했습니다. 연령 제한이 없는 정책도 포함했습니다." % (a, len(L)), [("홈", "/"), ("나이별", "/age/"), ("만 %d세" % a, "/age/%d/" % a)], "0.6")
    write("/age/", layout("/age/", "나이별 청년정책", "만 19세부터 39세까지 나이별로 받을 수 있는 청년정책을 확인하세요.",
                          '<div class="page-head"><h1>나이별 청년정책</h1></div>' + ad() + '<div class="chips">%s</div>' % "".join('<a class="chip" href="/age/%d/">만 %d세</a>' % (a, a) for a in range(19, 40)), None, [("홈", "/"), ("나이별", "/age/")]), "0.8")
    # 키워드·마감 임박·상시
    for t, L in by_kw.items():
        if ("kw", t) in hubs_ok:
            hub("/keyword/%s/" % t, "%s 청년정책 %d개" % (t, len(L)), "%s 관련 청년정책" % t, L, "", 100, "%s 청년정책 %d개 - 신청 대상·기간" % (t, len(L)), "%s 관련 청년정책 %d개의 신청 대상과 기간을 정리했습니다." % (t, len(L)), [("홈", "/"), (t, "/keyword/%s/" % t)], "0.6")
    soon = [p for p in ps if p["status"] == "진행" and (p["end"] - TODAY).days <= 14]
    hub("/closing/", "신청 마감이 임박한 청년정책 %d개" % len(soon), "2주 안에 신청이 끝나는 정책", soon, "", 100, "마감 임박 청년정책 %d개 - 2주 안에 신청 종료" % len(soon), "2주 안에 신청이 끝나는 청년정책 %d개를 마감일 순으로 정리했습니다." % len(soon), [("홈", "/"), ("마감 임박", "/closing/")], "0.8")
    always = [p for p in ps if p["status"] == "상시"]
    hub("/always/", "상시 신청 청년정책 %d개" % len(always), "기간 제한 없이 언제든 신청할 수 있는 정책", always, "", 100, "상시 신청 청년정책 %d개 - 언제든 신청 가능" % len(always), "기간 제한 없이 상시 신청할 수 있는 청년정책 %d개를 분야별로 정리했습니다." % len(always), [("홈", "/"), ("상시 신청", "/always/")], "0.8", sort=False)
    # 홈
    kwc = [t for t, L in sorted(by_kw.items(), key=lambda kv: -len(kv[1])) if ("kw", t) in hubs_ok][:12]
    body = ['<div class="hero"><h1>나에게 맞는 청년정책 찾기</h1><p>정부·지자체 청년정책 %d개를 분야·지역·나이별로 확인하세요(온통청년 공공데이터)</p>'
            '<div class="today-box"><div><small>신청 가능 정책</small><b>%d개</b></div><div><small>상시 신청</small><b>%d개</b></div><div><small>2주 안에 마감</small><b>%d개</b></div><div><small>기준일</small><b>%s</b></div></div></div>' % (len(ps), len(ps), len(always), len(soon), fmt(TODAY)),
            '<div class="search-box"><input id="q" type="search" placeholder="정책 검색 (예: 월세, 교통비, 면접, 창업)" autocomplete="off"><div id="sr" class="sr-list"></div></div>', ad(),
            '<h2 class="group-title">분야별</h2><div class="card-grid">%s</div>' % cards.replace(cards, "".join('<a class="card" href="/category/%s/"><b>%s</b><span>%d개 · %s</span></a>' % (k, esc(v), len(by_c[v]), esc(CAT_DESC[k])) for k, v in CATS.items())),
            '<h2 class="group-title">지역별</h2><div class="chips">%s</div>' % ('<a class="chip" href="/nationwide/">전국 대상 <small>%d</small></a>' % len(nat) + "".join('<a class="chip" href="/region/%s/">%s <small>%d</small></a>' % (q(s), esc(s), len(by_sido[s])) for s in SIDOS if by_sido[s])),
            '<h2 class="group-title">인기 키워드</h2><div class="chips">%s</div>' % "".join('<a class="chip" href="/keyword/%s/">%s</a>' % (q(t), esc(t)) for t in kwc),
            '<h2 class="group-title">마감 임박</h2>' + ptable(soon[:8], 8), '<p><a class="chip" href="/closing/">마감 임박 전체 보기</a> <a class="chip" href="/always/">상시 신청 정책 보기</a> <a class="chip" href="/age/">나이별 보기</a></p>', '<script src="/assets/js/search.js"></script>']
    faq = [("청년정책은 몇 살까지 신청할 수 있나요?", "정책마다 다르며 대부분 만 19~39세(일부는 34세·45세·49세)를 대상으로 합니다. 정책 상세에서 대상 연령을 확인하세요."),
           ("정보는 어디서 가져왔나요?", "한국고용정보원 온통청년 청년정책 Open API를 매일 받아 정리합니다. 신청 기간이 끝난 정책과 마감 표시된 정책은 싣지 않습니다."),
           ("여기서 바로 신청할 수 있나요?", "이 사이트는 정보를 정리해 안내합니다. 신청은 각 정책의 신청 페이지(운영기관)에서 하며, 자격과 기간은 공고를 꼭 확인하세요.")]
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "우아청년정책", "url": BASE + "/", "potentialAction": {"@type": "SearchAction", "target": BASE + "/?q={q}", "query-input": "required name=q"}}]
    write("/", layout("/", "청년정책 찾기 - 신청 가능 %d개 지원금·주거·일자리 | 우아청년정책" % len(ps), "정부·지자체 청년정책 %d개를 분야·지역·나이별로 확인하세요. 청년 월세·교통비·취업·창업 지원을 신청 기간과 함께 정리했습니다." % len(ps), "\n".join(body), faq, None, "website", ld), "1.0")
    idx = [[p["name"], "/policy/%s/" % p["id"], p["cat"], region_txt(p), ""] for p in ps]
    (OUT / "search_index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pages_static()
    finish()


def pages_static():
    body = ['<div class="page-head"><h1>청년정책 신청 가이드</h1></div>', ad(),
            '<h2 class="group-title">1. 나에게 맞는 정책 찾기</h2><ol class="lead"><li><a href="/age/">나이별</a>·<a href="/category/">분야별</a>·<a href="/region/">지역별</a>로 후보를 좁힙니다.</li><li>정책 상세에서 대상 연령, 소득 조건, 추가 자격을 확인합니다.</li><li>신청 기간을 확인하고 <a href="/closing/">마감 임박</a> 정책부터 챙깁니다. 기간 제한이 없는 <a href="/always/">상시 신청</a> 정책도 있습니다.</li></ol>',
            '<h2 class="group-title">2. 신청 전 확인할 것</h2><ul class="lead"><li>거주지(주민등록 주소지) 요건이 있는 정책이 많습니다. 이사 계획이 있다면 전입 시점도 확인하세요.</li><li>소득·재산 기준은 중위소득 비율이나 연소득 금액으로 정해지며 정책마다 다릅니다.</li><li>중복 수급이 안 되는 정책이 있으니 이미 받는 지원과 겹치는지 공고에서 확인하세요.</li></ul>',
            '<div class="note-box">이 사이트는 공공데이터를 정리한 참고용이며 신청 자격·금액은 운영기관 공고가 기준입니다. 신청은 해당 기관 페이지에서 직접 진행하세요.</div>']
    write("/guide/", layout("/guide/", "청년정책 신청 가이드", "청년정책을 찾고 신청 전에 확인할 점을 정리했습니다.", "\n".join(body), None, [("홈", "/"), ("이용 안내", "/guide/")]), "0.4")
    body = ['<div class="page-head"><h1>데이터 설명</h1></div>', '<p class="lead">우아청년정책은 한국고용정보원 <b>온통청년 청년정책 Open API</b>(공공데이터포털 15143273 연결, 이용허락범위 제한 없음)를 매일 받아 정리합니다. 신청 기간이 끝난 정책과 마감으로 표시된 정책은 제외하고, 상시 신청 정책과 진행·예정 정책만 싣습니다. 정책 지역은 API의 시군구 코드를 시도로 묶었으며 일부 시군구 이름은 운영기관 이름에서 추정했습니다. 정책 내용은 등록기관이 작성한 원문을 정리한 것입니다.</p>']
    write("/about/", layout("/about/", "데이터 설명", "우아청년정책이 사용하는 온통청년 청년정책 데이터를 설명합니다.", "\n".join(body), None, [("홈", "/"), ("데이터 설명", "/about/")]), "0.3")
    body = ['<div class="page-head"><h1>개인정보처리방침</h1></div>', '<p class="lead">우아청년정책은 회원가입·로그인 없이 이용하며 개인정보를 수집하지 않습니다. 사이트 개선을 위해 Google Analytics를 사용하고, 광고 게재를 위해 Google AdSense와 쿠팡 파트너스를 사용하며 이 과정에서 쿠키가 사용될 수 있습니다.</p>']
    write("/privacy/", layout("/privacy/", "개인정보처리방침", "우아청년정책 개인정보처리방침", "\n".join(body), None, [("홈", "/"), ("개인정보처리방침", "/privacy/")]), sitemap=False)


def finish():
    shutil.copytree(ROOT / "assets", OUT / "assets")
    for nf in ROOT.glob("naver*.html"):
        shutil.copy(nf, OUT / nf.name)
    today = TODAY.isoformat()
    urls = "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (BASE, q(p), today, pr) for p, pr in WRITTEN)
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE, encoding="utf-8")
    (OUT / "CNAME").write_text("wooayouth.wooahouse.com\n", encoding="utf-8")
    nf = layout("/404.html", "페이지를 찾을 수 없습니다", "요청한 페이지를 찾을 수 없습니다. 마감된 정책 페이지는 삭제될 수 있습니다.", '<div class="page-head"><h1>페이지를 찾을 수 없습니다</h1><p>마감된 정책 페이지는 삭제됩니다.</p></div><div class="chips"><a class="chip" href="/">홈으로</a><a class="chip" href="/category/">분야별</a><a class="chip" href="/closing/">마감 임박</a></div>', None, None, noindex=True)
    (OUT / "404.html").write_text(nf, encoding="utf-8")
    print("페이지", len(WRITTEN), "(sitemap)")


if __name__ == "__main__":
    build()
