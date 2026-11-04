#!/usr/bin/env bash
# 고른 시험지만 차례로 돌리고 요약(틀린 턴 · 점수 · 값)만 모은다(10-14 긴 작업에서 씀).
#   bash evals/tools/run_some.sh <태그> <시험지 이름...>
#   예) bash evals/tools/run_some.sh r6 weather_16 bus_20 places_30 long_100 adversarial_20 chuncheon_youth_60 probe_weak_28 rules_v6_16
# 키는 ../big-contest/.env 를 --env-file 로 읽기만 한다(다른 PC면 ENV_FILE=경로 로 바꿈).
# 요약 로그: evals/results/logs/run_<태그>.log, 결과 파일: evals/results/<시험지>_<날짜>_<태그>.json
TAG="$1"; shift
cd "$(dirname "$0")/../.." || exit 1
ENV_FILE="${ENV_FILE:-../big-contest/.env}"
mkdir -p evals/results/logs
OUT="evals/results/logs/run_${TAG}.log"
: > "$OUT"
for sc in "$@"; do
  echo "=== $sc $(date -u -d '+9 hours' '+%H:%M')" >> "$OUT"
  PYTHONIOENCODING=utf-8 uv run python evals/run_long.py --scenario "evals/scenarios/${sc}.json" \
    --env-file "$ENV_FILE" --tag "$TAG" 2>&1 | grep -E "^ *[0-9]+ X |\"all\"|\"usd\"|크레딧" >> "$OUT"
done
echo "=== 끝 $(date -u -d '+9 hours' '+%H:%M')" >> "$OUT"
