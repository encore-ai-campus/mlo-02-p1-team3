# 데이터 품질·실행 증빙

이 문서는 평가자가 수집·전처리·품질검증·적재 결과를 확인할 때 보는 기준과 기록 위치를 설명합니다.

## 실행 명령

```bash
python pipeline/run_pipeline.py --region "서울특별시 강남구" --limit 50
```

DB 적재를 포함할 때는 `--load-db`를 추가합니다. API 키가 없거나 외부 API가 실패한 경우에도 로그에는 단계별 오류와 `loaded_count`가 남습니다.

## 검증 항목

1. 원본 API 응답을 `output/raw/`에 보존합니다.
2. 정제 결과의 표준 컬럼과 행 수를 확인합니다.
3. 시설명·주소 누락과 중복을 계산합니다.
4. 위도·경도 및 수치형 필드의 변환 실패를 분리합니다.
5. 원본에 값이 있었지만 정제 결과에서 `NULL` 또는 빈 문자열이 된 필드를 기록합니다.
6. 검증 통과 결과를 설정된 `DATABASE_URL`로 적재합니다. 운영 환경에서는 Supabase가 제공하는 PostgreSQL 데이터베이스에 연결합니다.

## 로그 필드

```json
{
  "run_id": "20260928T120000Z-abc123",
  "region": "서울특별시 강남구",
  "collected_count": 50,
  "normalized_count": 50,
  "loaded_count": 50,
  "quality_status": "CHECK_PASSED",
  "load_status": "loaded",
  "errors": []
}
```

실제 수치는 실행 시 생성되는 `logs/pipeline-YYYYMMDD.jsonl`에서 확인합니다. 위 JSON은 필드 형식을 보여주는 예시입니다.
