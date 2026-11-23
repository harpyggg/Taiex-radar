import csv
import datetime as dt
import os
import random
import time
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
import requests

# ==============================================================================
# 0. 目錄設定（支援 GitHub / 本機環境變數，也相容 Colab）
# ==============================================================================
DEFAULT_DRIVE_BASE = "/content/drive/MyDrive/期交所資料/TAIFEX"


def get_raw_root_dir() -> str:
  env_raw = os.environ.get("TAIFEX_RAW_DIR", "").strip()
  if env_raw:
    return env_raw

  env_base = os.environ.get("TAIFEX_BASE_DIR", "").strip()
  if env_base:
    return os.path.join(env_base, "Raw_TAIFEX")

  if os.path.exists("/content/drive/MyDrive"):
    return os.path.join(DEFAULT_DRIVE_BASE, "Raw_TAIFEX")

  return os.path.join("data", "Raw_TAIFEX")


RAW_DIR = get_raw_root_dir()
SUB_DIRS = {
    "fut_TX": os.path.join(RAW_DIR, "futData_TX"),
    "fut_MTX": os.path.join(RAW_DIR, "futData_MTX"),
    "fut_TMF": os.path.join(RAW_DIR, "futData_TMF"),
    "opt_TXO": os.path.join(RAW_DIR, "optData_TXO"),
    "pc_ratio": os.path.join(RAW_DIR, "pcRatio_TXO"),
    "fut_inst": os.path.join(RAW_DIR, "futContractsDate"),
}
for p in [RAW_DIR, *SUB_DIRS.values()]:
  os.makedirs(p, exist_ok=True)

# ==============================================================================
# 1. 執行參數設定（可由環境變數覆寫）
# ==============================================================================
TZ_TAIPEI = dt.timezone(dt.timedelta(hours=8))
TODAY_TAIPEI_STR = dt.datetime.now(TZ_TAIPEI).strftime("%Y/%m/%d")

TEST_SINGLE_DATE = os.environ.get("TEST_SINGLE_DATE", TODAY_TAIPEI_STR).strip()
RUN_STAGE_B = os.environ.get("RUN_STAGE_B", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
RANGE_START = os.environ.get("RANGE_START", "2026/11/20").strip()
RANGE_END = os.environ.get("RANGE_END", "2026/11/23").strip()
CHUNK_DAYS_GENERAL = 7
CHUNK_DAYS_INST = 1

FUT_DATA_URL = "https://www.taifex.com.tw/cht/3/futDataDown"
FUT_DATA_REF = "https://www.taifex.com.tw/cht/3/futDailyMarketView"
OPT_DATA_URL = "https://www.taifex.com.tw/cht/3/optDataDown"
OPT_DATA_REF = "https://www.taifex.com.tw/cht/3/optDailyMarketView"
PC_RATIO_URL = "https://www.taifex.com.tw/cht/3/pcRatioDown"
PC_RATIO_REF = "https://www.taifex.com.tw/cht/3/pcRatio"
FUT_INST_MOTHER_URL = "https://www.taifex.com.tw/cht/3/futContractsDate"
FUT_INST_DOWN_URL = "https://www.taifex.com.tw/cht/3/futContractsDateDown"


# ==============================================================================
# 2. HTTP Session、編碼、分類與欄位對齊工具
# ==============================================================================
def create_taifex_session() -> requests.Session:
  session = requests.Session()
  session.headers.update({
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/129.0.0.0 Safari/537.36"
      ),
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
      "Origin": "https://www.taifex.com.tw",
      "Connection": "keep-alive",
  })
  return session


def decode_taifex_bytes(content: bytes) -> str:
  for enc in ("cp950", "big5", "utf-8-sig", "utf-8"):
    try:
      return content.decode(enc)
    except UnicodeDecodeError:
      continue
  return content.decode("cp950", errors="replace")


def classify_response(content: bytes) -> Tuple[str, str]:
  if not content or len(content.strip()) < 20:
    return "EMPTY", ""
  text = decode_taifex_bytes(content)
  head_lower = text[:1000].lower()

  if (
      "datetime error" in head_lower
      or "日期時間錯誤" in text[:1000]
      or "futcontractsdateview" in head_lower
  ):
    return "DATE_ERR", text

  if (
      "查無資料" in text[:1500]
      or "無任何資料" in text[:1500]
      or "no data" in head_lower
  ):
    return "NO_DATA", text

  if (
      "<html" in head_lower
      or "<!doctype" in head_lower
      or "<script" in head_lower
  ):
    return "HTML_ERR", text

  lines = [ln for ln in text.splitlines() if ln.strip()]
  if len(lines) >= 2 and "," in lines[0]:
    return "VALID_CSV", text

  if len(lines) == 1 and "," in lines[0]:
    return "NO_DATA", text

  return "HTML_ERR", text


def align_csv_file(filepath: str, encoding: str = "cp950") -> None:
  """將 CSV 每一列欄位數對齊到標題列（去除尾端多餘逗號或補齊缺漏欄位）。"""
  with open(filepath, "r", encoding=encoding, errors="replace", newline="") as f:
    rows = list(csv.reader(f))
  if not rows:
    return

  header = [h.strip() for h in rows[0]]
  while header and header[-1] == "":
    header.pop()

  expected_len = len(header)
  if expected_len == 0:
    return

  aligned_rows = [header]
  for r in rows[1:]:
    if not any(c.strip() for c in r):
      continue
    if len(r) > expected_len:
      r = r[:expected_len]
    elif len(r) < expected_len:
      r = r + [""] * (expected_len - len(r))
    aligned_rows.append(r)

  with open(filepath, "w", encoding=encoding, newline="") as f:
    writer = csv.writer(f)
    writer.writerows(aligned_rows)


def post_with_retry(
    session: requests.Session,
    url: str,
    data: Dict[str, str],
    referer: str,
    timeout: Tuple[int, int] = (15, 90),
    max_retries: int = 4,
) -> Tuple[str, bytes, str]:
  headers = {"Referer": referer}
  last_err = ""
  for attempt in range(1, max_retries + 1):
    try:
      resp = session.post(url, data=data, headers=headers, timeout=timeout)
      if resp.status_code == 200:
        status, text = classify_response(resp.content)
        if status in ("VALID_CSV", "NO_DATA", "DATE_ERR"):
          return status, resp.content, text
        last_err = f"非預期內容({status}, {len(resp.content)} bytes)"
      else:
        last_err = f"HTTP {resp.status_code}"
    except (
        requests.exceptions.ReadTimeout,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ConnectionError,
    ) as e:
      last_err = f"{type(e).__name__}: {e}"
    except Exception as e:
      last_err = f"Unexpected {type(e).__name__}: {e}"

    wait_sec = min(30, (2**attempt) + random.uniform(0.5, 2.0))
    print(
        f"    [重試 {attempt}/{max_retries}] {url} 失敗 ({last_err})，等待"
        f" {wait_sec:.1f}s..."
    )
    time.sleep(wait_sec)

  return "FAILED", b"", last_err


def save_csv_bytes(
    filepath: str, content: bytes, text_preview: str, label: str
) -> None:
  with open(filepath, "wb") as f:
    f.write(content)
  align_csv_file(filepath, encoding="cp950")
  lines = [ln for ln in text_preview.splitlines() if ln.strip()]
  print(f"  [OK] {label} -> {filepath} ({len(content):,} bytes, {len(lines)} 行)")


# ==============================================================================
# 3. 三大法人期貨未平倉 (futContractsDateDown)
# ==============================================================================
def inspect_fut_contracts_mother_page(
    session: requests.Session,
) -> Dict[str, str]:
  print(f"[初始化] GET 母頁建立 Session: {FUT_INST_MOTHER_URL}")
  resp = session.get(FUT_INST_MOTHER_URL, timeout=(15, 30))
  resp.raise_for_status()
  soup = BeautifulSoup(resp.text, "html.parser")
  form_fields: Dict[str, str] = {}
  for inp in soup.find_all("input"):
    name = inp.get("name")
    if name:
      form_fields[name] = inp.get("value", "")
  return form_fields


def build_fut_inst_candidates(
    start_date: str, end_date: str
) -> List[Tuple[str, Dict[str, str]]]:
  candidates = [
      (
          "Mode_A_Range_NoCommodity",
          {"queryStartDate": start_date, "queryEndDate": end_date},
      ),
      (
          "Mode_B_Range_WithDownType",
          {
              "down_type": "1",
              "queryStartDate": start_date,
              "queryEndDate": end_date,
          },
      ),
      (
          "Mode_C_Range_WithQueryType",
          {
              "queryType": "1",
              "doQuery": "1",
              "queryStartDate": start_date,
              "queryEndDate": end_date,
          },
      ),
  ]
  if start_date == end_date:
    candidates.append((
        "Mode_D_SingleDate_MotherFields",
        {
            "queryType": "1",
            "goDay": "",
            "doQuery": "1",
            "dateaddcnt": "",
            "queryDate": start_date,
        },
    ))
    candidates.append((
        "Mode_E_BothDateFields",
        {
            "queryType": "1",
            "doQuery": "1",
            "queryDate": start_date,
            "queryStartDate": start_date,
            "queryEndDate": end_date,
        },
    ))
  return candidates


def fetch_fut_contracts_date(
    session: requests.Session,
    start_date: str,
    end_date: str,
    save_path: str,
    preferred_mode: Optional[str] = None,
) -> Optional[str]:
  candidates = build_fut_inst_candidates(start_date, end_date)
  if preferred_mode:
    candidates.sort(key=lambda x: 0 if x[0] == preferred_mode else 1)

  for mode_name, payload in candidates:
    status, content, text = post_with_retry(
        session=session,
        url=FUT_INST_DOWN_URL,
        data=payload,
        referer=FUT_INST_MOTHER_URL,
        timeout=(15, 90),
        max_retries=3,
    )
    if status == "VALID_CSV":
      save_csv_bytes(
          save_path, content, text, f"futContractsDateDown ({mode_name})"
      )
      return mode_name
    if status == "NO_DATA":
      print(f"  [SKIP] {start_date}~{end_date} 休市或查無資料 ({mode_name})")
      return preferred_mode or mode_name
    if status == "DATE_ERR":
      time.sleep(1.0)
      continue
    print(f"  [失敗] {mode_name} -> {status}: {text[:200]}")
    time.sleep(1.5)
  return None


# ==============================================================================
# 4. 一般下載端點
# ==============================================================================
def fetch_standard_endpoint(
    session: requests.Session,
    name: str,
    url: str,
    referer: str,
    payload: Dict[str, str],
    save_path: str,
) -> bool:
  if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
    print(f"  [略過] 已存在有效檔案: {save_path}")
    return True

  status, content, text = post_with_retry(
      session=session,
      url=url,
      data=payload,
      referer=referer,
      timeout=(15, 60),
      max_retries=4,
  )
  if status == "VALID_CSV":
    save_csv_bytes(save_path, content, text, name)
    return True
  if status == "NO_DATA":
    print(f"  [SKIP] {name} 該區間休市或查無資料")
    return True
  print(f"  [ERROR] {name} 抓取失敗 ({status}): {text[:200]}")
  return False


# ==============================================================================
# 5. 主流程
# ==============================================================================
def iter_date_chunks(start_str: str, end_str: str, chunk_days: int):
  d0 = dt.datetime.strptime(start_str, "%Y/%m/%d")
  d1 = dt.datetime.strptime(end_str, "%Y/%m/%d")
  cur = d0
  while cur <= d1:
    nxt = min(cur + dt.timedelta(days=chunk_days - 1), d1)
    yield cur.strftime("%Y/%m/%d"), nxt.strftime("%Y/%m/%d")
    cur = nxt + dt.timedelta(days=1)


def normalize_slash_date(raw: str) -> str:
  cleaned = raw.strip().replace("-", "/")
  parsed = dt.datetime.strptime(cleaned, "%Y/%m/%d")
  return parsed.strftime("%Y/%m/%d")


def run_single_day(
    session: requests.Session, date_slash: str, winning_mode: Optional[str]
) -> Optional[str]:
  tag = date_slash.replace("/", "")
  inst_path = os.path.join(
      SUB_DIRS["fut_inst"], f"futContractsDate_{tag}_{tag}.csv"
  )
  mode = fetch_fut_contracts_date(
      session=session,
      start_date=date_slash,
      end_date=date_slash,
      save_path=inst_path,
      preferred_mode=winning_mode,
  )
  if not mode:
    print(
        f"  [INFO] {date_slash} 三大法人未取得資料（可能為非交易日或尚未公布）。"
    )
    return winning_mode

  time.sleep(random.uniform(1.2, 2.0))
  for comm in ("TX", "MTX", "TMF"):
    fetch_standard_endpoint(
        session=session,
        name=f"futDataDown_{comm}",
        url=FUT_DATA_URL,
        referer=FUT_DATA_REF,
        payload={
            "down_type": "1",
            "commodity_id": comm,
            "commodity_id2": "",
            "commodity_id2t": "all",
            "queryStartDate": date_slash,
            "queryEndDate": date_slash,
        },
        save_path=os.path.join(
            SUB_DIRS[f"fut_{comm}"], f"futData_{comm}_{tag}_{tag}.csv"
        ),
    )
    time.sleep(random.uniform(1.0, 1.8))

  fetch_standard_endpoint(
      session=session,
      name="optDataDown_TXO",
      url=OPT_DATA_URL,
      referer=OPT_DATA_REF,
      payload={
          "down_type": "1",
          "commodity_id": "TXO",
          "queryStartDate": date_slash,
          "queryEndDate": date_slash,
      },
      save_path=os.path.join(
          SUB_DIRS["opt_TXO"], f"optData_TXO_{tag}_{tag}.csv"
      ),
  )
  time.sleep(random.uniform(1.0, 1.8))

  fetch_standard_endpoint(
      session=session,
      name="pcRatioDown_TXO",
      url=PC_RATIO_URL,
      referer=PC_RATIO_REF,
      payload={
          "queryStartDate": date_slash,
          "queryEndDate": date_slash,
      },
      save_path=os.path.join(SUB_DIRS["pc_ratio"], f"pcRatio_{tag}_{tag}.csv"),
  )
  return mode


def run_step1() -> None:
  print(f"[設定] 輸出根目錄: {RAW_DIR}")
  session = create_taifex_session()
  inspect_fut_contracts_mother_page(session)
  time.sleep(1.0)

  env_target_date = os.environ.get("TARGET_DATE", "").strip()
  if env_target_date:
    single_dt = normalize_slash_date(env_target_date)
    print(f"=== Step 1 單日模式（TARGET_DATE）: {single_dt} ===")
    run_single_day(session, single_dt, winning_mode="Mode_A_Range_NoCommodity")
    print("=== Step 1 完成 ===")
    return

  single_dt = normalize_slash_date(TEST_SINGLE_DATE)
  print(f"=== Step 1 單日模式: {single_dt} ===")
  winning_mode = run_single_day(
      session, single_dt, winning_mode="Mode_A_Range_NoCommodity"
  )

  if not RUN_STAGE_B:
    print("=== Step 1 完成（RUN_STAGE_B=False） ===")
    return

  start_dt = normalize_slash_date(RANGE_START)
  end_dt = normalize_slash_date(RANGE_END)
  print(f"=== Step 1 區間模式: {start_dt} ~ {end_dt} ===")

  inst_chunk = (
      1 if winning_mode == "Mode_D_SingleDate_MotherFields" else CHUNK_DAYS_INST
  )
  for s_dt, e_dt in iter_date_chunks(start_dt, end_dt, inst_chunk):
    s_tag, e_tag = s_dt.replace("/", ""), e_dt.replace("/", "")
    out_path = os.path.join(
        SUB_DIRS["fut_inst"], f"futContractsDate_{s_tag}_{e_tag}.csv"
    )
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
      print(f"  [略過] 已存在: {out_path}")
      continue
    fetch_fut_contracts_date(
        session, s_dt, e_dt, out_path, preferred_mode=winning_mode
    )
    time.sleep(random.uniform(1.2, 2.2))

  for s_dt, e_dt in iter_date_chunks(start_dt, end_dt, CHUNK_DAYS_GENERAL):
    s_tag, e_tag = s_dt.replace("/", ""), e_dt.replace("/", "")
    for comm in ("TX", "MTX", "TMF"):
      fetch_standard_endpoint(
          session=session,
          name=f"futDataDown_{comm}",
          url=FUT_DATA_URL,
          referer=FUT_DATA_REF,
          payload={
              "down_type": "1",
              "commodity_id": comm,
              "commodity_id2": "",
              "commodity_id2t": "all",
              "queryStartDate": s_dt,
              "queryEndDate": e_dt,
          },
          save_path=os.path.join(
              SUB_DIRS[f"fut_{comm}"], f"futData_{comm}_{s_tag}_{e_tag}.csv"
          ),
      )
      time.sleep(random.uniform(1.0, 1.8))

    fetch_standard_endpoint(
        session=session,
        name="optDataDown_TXO",
        url=OPT_DATA_URL,
        referer=OPT_DATA_REF,
        payload={
            "down_type": "1",
            "commodity_id": "TXO",
            "queryStartDate": s_dt,
            "queryEndDate": e_dt,
        },
        save_path=os.path.join(
            SUB_DIRS["opt_TXO"], f"optData_TXO_{s_tag}_{e_tag}.csv"
        ),
    )
    time.sleep(random.uniform(1.0, 1.8))

    fetch_standard_endpoint(
        session=session,
        name="pcRatioDown_TXO",
        url=PC_RATIO_URL,
        referer=PC_RATIO_REF,
        payload={
            "queryStartDate": s_dt,
            "queryEndDate": e_dt,
        },
        save_path=os.path.join(
            SUB_DIRS["pc_ratio"], f"pcRatio_{s_tag}_{e_tag}.csv"
        ),
    )
    time.sleep(random.uniform(1.2, 2.0))

  print("=== Step 1 區間抓取完成 ===")


if __name__ == "__main__":
  run_step1()
