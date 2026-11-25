# 우아청년정책 (wooayouth)

한국고용정보원 온통청년 청년정책 Open API(`youthcenter.go.kr/go/ythip/getPlcy`, data.go.kr 15143273 연결형)로 만든 청년정책 정적 사이트(Python). https://wooayouth.wooahouse.com

- `scripts/fetch_data.py` — 전체 약 4천 건(40호출, pageSize 100) → `data/policies.json.gz`. 키는 환경변수 `YOUTH_API_KEY`(로컬: `../_newdata/youthcenter.env`). **키 유효기간 2026-09-09~2027-09-09 — 만료 전 온통청년에서 재신청.**
- `scripts/build_site.py` — 신청기간이 안 끝난 정책 + 상시(aplyPrdSeCd 0057002)만 페이지 생성(0057003=마감 제외, 약 1,450개). 분야·지역·나이별·키워드·마감임박·상시 허브. 시군구 이름은 코드 1개짜리 정책의 운영기관명 다수결로 추정.
- Actions: push + 매일 KST 05:30 수집→빌드(커밋 없음, 실패 시 커밋된 data로 빌드). 시크릿 `YOUTH_API_KEY`. 네이버 토큰은 `scripts/common.py` `NAVER_TOKEN`.
