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
(assign ticket ให้เป็นคนที่ run ตาม token ที่ใช้ — เฉพาะตอน run จริง ไม่ใช่ `--dry-run`) → `post_comment` (skip
ถ้าผลลัพธ์เหมือน comment ล่าสุดที่มี marker `Auto RSP Sync Check` อยู่แล้ว)

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
