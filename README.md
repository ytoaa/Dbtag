# Danbooru Tag Auto-Updater

Danbooru의 최신 태그를 공식 API에서 주기적으로 수집해 `data/danbooru_tags.csv`와 ComfyUI-Custom-Scripts 호환 `data/autocomplete.txt`를 생성합니다.

## 데이터 원천

공식 Danbooru API:

```text
https://danbooru.donmai.us/tags.json
https://danbooru.donmai.us/wiki_pages.json
```

사용 파라미터:

```text
limit=1000
search[hide_empty]=yes
search[is_deprecated]=no
search[order]=count
page=1..N
```

빈 배열 `[]`이 반환될 때까지 페이지를 순회합니다.
`alias` 컬럼은 wiki page의 `other_names`를 태그명과 매칭해 채웁니다.

## 출력 파일

CSV:

```text
data/danbooru_tags.csv
```

```csv
tag,category,count,alias
1girl,0,4974288,"女の子,女性,少女,girl,おんなのこ,女子,소녀,女孩,姑娘,女"
solo,0,4005860,"ソロ,solo,ひとり"
long_hair,0,3608339,"ロングヘアー,長髪,ロングヘア"
```

Autocomplete:

```text
data/autocomplete.txt
```

```txt
1girl,4974288
solo,4005860
long_hair,3608339
```

## 로컬 실행

```bash
python -m pip install -r requirements.txt
python scripts/fetch_danbooru_tags.py
```

기본 필터는 `MIN_COUNT=20`입니다.

```bash
MIN_COUNT=50 python scripts/fetch_danbooru_tags.py
```

테스트용으로 일부 페이지만 받을 수 있습니다.

```bash
python scripts/fetch_danbooru_tags.py --max-pages 1
```

```bash
python scripts/fetch_danbooru_tags.py --max-pages 1 --max-wiki-pages 1
```

## 자동 업데이트

GitHub Actions는 매주 월요일 오전 7시 KST에 실행됩니다.

```yaml
schedule:
  - cron: "0 22 * * 0"
```

GitHub Actions cron은 UTC 기준이므로 `0 22 * * 0`은 매주 일요일 22:00 UTC, 즉 매주 월요일 07:00 KST입니다.

## Danbooru category 값

| 값 | 의미 |
| -: | --- |
| 0 | general |
| 1 | artist |
| 3 | copyright |
| 4 | character |
| 5 | meta |

## Alias

`/wiki_pages.json`의 `other_names`를 사용합니다. wiki page가 없거나 `other_names`가 비어 있는 태그는 `alias` 컬럼을 빈 문자열로 유지합니다.
