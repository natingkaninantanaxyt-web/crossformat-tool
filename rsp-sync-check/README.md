# RSP Sync Check

เช็คตั๋ว Jira "RSP Sync : Effective on ..." ที่ยังไม่ปิด ว่าร้านค้าไหน sync ราคาแล้วบ้าง เทียบกับ log
`FetchRetailPrice` บน GCP (`tdshop-prod` / `PosApp`) แล้ว comment สรุปกลับที่ตั๋ว — เป็นหนึ่งโมดูลใน
[Front Automation Hub](../README.md)

## Repository overview

โมดูลนี้คือไฟล์ HTML ไฟล์เดียว (`index.html`) ที่ทำงานฝั่ง client ทั้งหมด ไม่มี build system, server,
หรือ backend ใดๆ — เปิดตรงในเบราว์เซอร์ได้เลย สี/ฟอนต์/โทนพื้นฐานดึงมาจาก [`../shared/theme.css`](../shared/theme.css)

**ต่างจาก CrossFormat ตรงที่ไม่มี "engine" ทำงานอยู่ในหน้าเว็บเลย** เพราะงานจริง (query `gcloud logging read`
และเรียก Jira REST API ด้วย personal token) ต้องรันจากเครื่องผู้ใช้เท่านั้น — browser ยิง request ตรงไปที่
`jira.tdshop.io` ไม่ได้ (CORS + ต้องมี credential) และไม่มีทางรัน `gcloud` จาก JS ในเบราว์เซอร์ หน้านี้จึงทำหน้าที่แค่:

1. ให้ดาวน์โหลด [`rsp_sync_check.py`](./rsp_sync_check.py) — สคริปต์ตัวจริงที่รันการเช็ค
2. โชว์คำสั่ง terminal สำหรับรัน (`--dry-run` หรือรันจริง)
3. รับ output ที่ผู้ใช้ copy-paste กลับมา แล้ว parse+render เป็นตารางอ่านง่าย (`parseOutput()` ใน `index.html`) — ประมวลผลในเบราว์เซอร์ล้วน ไม่ส่งข้อมูลไปที่ไหน

## `rsp_sync_check.py`

สคริปต์ python เดี่ยว ไม่มี dependency นอก stdlib ทำงาน stage หลักๆ: `search_open_rsp_tickets` (JQL: ticket
label `PS_Front` + summary มีคำว่า "RSP Sync" + ยังไม่ปิด) → `parse_ticket` (ดึง barcode/store list/effective
date จาก wiki-table ใน description ด้วย regex) → `query_synced_stores` (สร้าง `gcloud logging read` filter
จาก store list + barcode + event `FetchRetailPrice`) → diff เทียบ store list กับที่เจอใน log → `set_assignee`
(assign ticket ให้เป็นคนที่ run ตาม token ที่ใช้ — **เฉพาะถ้ายังไม่มี assignee เดิม** ไม่งั้นข้ามไปเลย) →
`post_comment` (skip ถ้าผลลัพธ์เหมือน comment ล่าสุดที่มี marker `Auto RSP Sync Check` อยู่แล้ว) → status/flag
transition (ดูหัวข้อด้านล่าง)

### Status transitions + flag

อิงจาก workflow จริงที่ทีมใช้ปิดตั๋วพวกนี้ด้วยมืออยู่แล้ว (เช็คจากตั๋วเก่าที่ปิดไปแล้วอย่าง SUP-13505/13506):

- **status = Open + ยังมีร้าน sync ไม่ครบ** → transition ไป **In Progress** + ติด flag `Impediment`
- **status = In Progress + sync ครบทุกร้านแล้ว** → เอา flag ออก + transition ไป **Close** พร้อมตั้ง
  `resolution = "Won't Do"` และ `fixVersions = ["Won't Fix Release"]`

Transition ID ไม่ได้ hardcode ไว้ — `get_transition_id` เรียก `/issue/{key}/transitions` สดทุกครั้งแล้วหาด้วย
**ชื่อ** transition ("In Progress" / "Close") เพื่อกันปัญหาถ้า workflow เปลี่ยน ID ในอนาคต ถ้าหาไม่เจอ (เช่น
workflow ถูกแก้ไปแล้ว) จะ print WARNING แล้วข้าม ไม่ทำให้ script ทั้งรอบ crash

**เรื่อง flag (`set_flag`):** field `customfield_10107` (Flagged) เซ็ตผ่าน `PUT /issue/{key}` ธรรมดาไม่ได้ —
Jira ตอบ 400 กับ `"errors": {"customfield_10107": "...not on the appropriate screen..."}` เพราะ field นี้ผูกกับ
ปุ่ม Flag บน board เท่านั้น ไม่ได้อยู่บน edit screen ไหนเลย ต้องยิงไปที่ endpoint ของปุ่มนั้นตรงๆ (ไม่มี doc
เป็นทางการ แต่ทดสอบแล้วใช้งานได้แน่นอน): `POST /rest/greenhopper/1.0/xboard/issue/flag/flag.json` body
`{"issueKeys": [key], "flag": true/false}`

**บั๊กที่เจอจากเรื่องนี้ (แก้แล้วใน v1.2.1):** `jira_request` เดิมเช็ค error จาก response แค่ key `errorMessages`
ซึ่ง Jira ตอบ error field-validation แบบข้างบนมาที่ key `errors` (คนละ key) แทน — HTTP 400 จริงแต่ `errorMessages`
เป็น `[]` (falsy) เลยไม่ raise exception ทำให้ script รายงานว่า "flagged" สำเร็จ ทั้งที่ Jira ไม่ได้เซ็ตอะไรให้เลย
แก้โดยให้ `jira_request` เช็ค **HTTP status code จริงจาก curl** (`-w "\n%{http_code}"`) แทนการเดาจาก shape ของ
response body — ครอบคลุม error ทุกแบบ ไม่ใช่แค่ที่ Jira เลือกจะใส่ใน `errorMessages`

เช็ค permission ของ token ผ่าน `/rest/api/2/mypermissions?projectKey=SUP` แล้วว่า `ASSIGN_ISSUES`,
`EDIT_ISSUES`, `TRANSITION_ISSUES`, `RESOLVE_ISSUES` ทุกตัว = true สำหรับ token ที่ทดสอบไว้ — token คนอื่นในทีม
ที่ role เดียวกันควรจะผ่านหมดเหมือนกัน แต่ถ้า role ต่างกันอาจต้องเช็คซ้ำ

**Jira credential** resolve ตามลำดับ (ดู `load_jira_creds`) เพื่อให้ทุกคนในทีมรันได้ ไม่ต้องพึ่ง Claude Code:
1. env vars `JIRA_URL` / `JIRA_PERSONAL_TOKEN`
2. config file `~/.rsp_sync_check.json` (`{"jira_url": ..., "jira_token": ...}`)
3. fallback: `~/.claude.json` (`mcpServers.mcp-atlassian.env`) — สำหรับคนที่ใช้ Claude Code อยู่แล้ว

ไม่มี token ฝังอยู่ในไฟล์นี้เลยไม่ว่ากรณีไหน ปลอดภัยที่จะ commit ขึ้น public repo เพราะ credential จริงอยู่แค่บนเครื่อง
ผู้ใช้เท่านั้น เรียก Jira ผ่าน `curl` (ไม่ใช่ Python `urllib`) เพราะ certifi bundle ของ Python ไม่มี CA ขององค์กร
ที่ใช้เซ็น cert ของ `jira.tdshop.io` แต่ macOS system trust store (ที่ `curl` ใช้) มี

## Versioning / staleness check

`SCRIPT_VERSION` ใน `rsp_sync_check.py` ต้อง**ตรงกับไฟล์ [`VERSION`](./VERSION)** เสมอ — ทุกครั้งที่แก้ logic ในสคริปต์
ต้อง bump ทั้งสองที่คู่กัน (`VERSION` เก็บแค่เลขเวอร์ชันดิบๆ ไม่มี newline พิเศษอะไร) เพราะตัวสคริปต์จะ fetch ไฟล์
`VERSION` จาก `raw.githubusercontent.com` ทุกครั้งที่ run (`check_for_updates`) มาเทียบกับ `SCRIPT_VERSION` ของตัวเอง
ถ้าไม่ตรงจะเตือนผู้ใช้ว่าไฟล์ที่โหลดไว้เก่าแล้ว ให้ไปโหลดใหม่ก่อน (ถาม y/N ว่าจะรันต่อทั้งที่เก่าไหม) — ถ้าลืม bump
`VERSION` ตอน push การเตือนนี้จะไม่ทำงาน ผู้ใช้เก่าจะไม่รู้ตัวว่าไฟล์ตัวเองล้าสมัยไปแล้ว

## Running / developing

- เปิด `rsp-sync-check/index.html` ตรงในเบราว์เซอร์ ไม่ต้อง install อะไร
- ทดสอบ `rsp_sync_check.py` แยกจากหน้าเว็บได้เลย: `python3 rsp_sync_check.py --dry-run` (ต้อง `gcloud auth login`
  และมี credential ตามที่ระบุไว้ข้างบนก่อน) เพิ่ม `--skip-update-check` ถ้าไม่อยากให้เช็คเวอร์ชันตอนเทส
- ถ้าแก้ logic ใน `rsp_sync_check.py` ต้อง sync ให้ตรงกับตัวต้นฉบับที่ `~/scripts/rsp_sync_check/rsp_sync_check.py`
  บนเครื่อง (ใช้รันแบบ manual/cron ได้เหมือนกัน) — สองไฟล์นี้เป็นคนละไฟล์ ไม่ได้ symlink กัน
