# CrossFormat

เครื่องมือแปลงไฟล์ Excel ทะเบียนร้านค้า ให้เป็นไฟล์ `.txt` แบบ pipe-delimited สำหรับขั้นตอน onboarding
QR API ของพาร์ตเนอร์ พร้อมตรวจสอบโครงสร้างไฟล์ให้อัตโนมัติ — เป็นหนึ่งโมดูลใน [Front Automation Hub](../README.md)

## Repository overview

โมดูลนี้คือไฟล์ HTML ไฟล์เดียว (`index.html`) ที่ทำงานฝั่ง client ทั้งหมด ไม่มี build system, package manager,
test suite, หรือ server — เปิดไฟล์ตรงในเบราว์เซอร์ได้เลย สี/ฟอนต์/โทนพื้นฐานดึงมาจาก
[`../shared/theme.css`](../shared/theme.css) ซึ่งใช้ร่วมกับหน้า Hub และโมดูลอื่นในอนาคต

## Running / developing

- เปิด `crossformat/index.html` ตรงในเบราว์เซอร์ (เช่น `open crossformat/index.html` บน macOS) ไม่ต้อง install, ไม่ต้อง dev server, ไม่ต้อง bundler
- ต้องมีอินเทอร์เน็ตให้หน้าเว็บโหลด CDN dependencies ใน `<head>`: SheetJS (`xlsx@0.18.5`) สำหรับอ่าน Excel, Font Awesome สำหรับไอคอน, Google Fonts (Inter/Outfit/JetBrains Mono)
- เพราะเป็น static file ล้วน "การเทสต์" หลังแก้โค้ด = reload หน้าในเบราว์เซอร์แล้วลองแปลงไฟล์ `.xlsx`/`.xls` ตัวอย่างดู

## Architecture

โค้ดแบ่งเป็นสามส่วนใน `index.html`: `<style>` (คอมโพเนนต์เฉพาะของโมดูลนี้ — ส่วน design tokens/reset/body อยู่ใน `../shared/theme.css`), HTML markup (สอง tab), และ `<script>` ก้อนเดียวที่รวม logic ทั้งหมด ไม่มี module system — ฟังก์ชันทั้งหมดเป็น global และผูกผ่าน `document.addEventListener`/`getElementById` ใน `initEventListeners`/`initDragAndDrop`/`initSettingsPanel` ที่เรียกจาก `DOMContentLoaded` handler เดียว

### Global state

`state` object เดียวเก็บทุกอย่าง: header template สองชุด (`templateRow1`, `templateRow3`), รายการไฟล์ที่อัปโหลด (แต่ละไฟล์มี `rows` ที่ parse แล้ว, `status` เป็น `passed`/`error`, และ `logs`), `outputText` ที่ generate ได้, และ `outputIssues`/`outputStats` จากการตรวจสอบ output Template ถูกเก็บไว้ใน `localStorage` ที่ key `df_template_row1_arr` / `df_template_row3_arr` (ดู `loadTemplate`/`saveTemplate`) ส่วนที่เหลืออยู่แค่ในหน่วยความจำ รีโหลดแล้วหาย

### Expected Excel layout

ไฟล์ Excel ที่อัปโหลด (ใช้แค่ sheet แรก) ต้องมีโครงสร้างตายตัวแบบ 4 แถวขึ้นไป:
- **แถว 1** (index 0): ชื่อ header ระดับ global — ตรวจกับ `state.templateRow1` (default: `recordType, functionName, fileDate, fileNum, partnerID, totalRecordNum`)
- **แถว 2** (index 1): ค่า header ระดับ global — ใช้แถว 2 ของไฟล์ที่ผ่านการตรวจไฟล์แรกเท่านั้น `fileDate`, `partnerID`, `totalRecordNum` จะถูก override ตอน generate output จาก date picker/partner-ID input/จำนวน record ที่คำนวณได้ (ดู `generateOutputText`)
- **แถว 3** (index 2): ชื่อ column ข้อมูลร้านค้า — ตรวจกับ `state.templateRow3` (ลิสต์ยาวกว่า ~60 columns หลายตัวมีคำอธิบายภาษาไทยฝังอยู่ในตัว header เอง เช่น `"addressNo\n(M)\n(เลขที่ตั้งสาขา)"`)
- **แถว 4 เป็นต้นไป** (index 3+): ค่าข้อมูลร้านค้า แถวละ 1 record แถวว่าง (`isRowEmpty`) จะถูกข้าม ดึงมาจาก**ทุกไฟล์**ที่อัปโหลดและผ่านการตรวจ ไม่ใช่แค่ไฟล์แรก

### Conversion & validation pipeline

`handleExcelFiles` → parse แต่ละไฟล์ด้วย `XLSX.utils.sheet_to_json(sheet, {header: 1})` แล้ว push raw record เข้า `state.uploadedFiles` จากนั้นเรียก `processUploadedFiles` ซึ่งเป็น pipeline หลักที่รันซ้ำทุกครั้งที่ไฟล์/template/input วันที่-partner ID เปลี่ยน:

1. `compareHeaders` — normalize (ผ่าน `normalizeHeader` ที่ลบ newline/BOM/zero-width chars และรวม smart quotes ให้เป็นแบบเดียวกัน) แล้ว diff header จริงกับที่คาดไว้ทีละตำแหน่ง ทั้งแถว 1 และแถว 3 ต่อไฟล์
2. เช็คว่ามีอย่างน้อย 1 แถวข้อมูลร้านค้าที่ไม่ว่างตั้งแต่แถว 4 เป็นต้นไป
3. `generateOutputText` — สร้าง output แบบ pipe-delimited: header 1 บรรทัด (จากแถว 2 ของไฟล์แรกที่ผ่าน, จำนวน column = `templateRow1.length`) ตามด้วย record ร้านค้าทีละบรรทัดจากทุกไฟล์ที่ผ่าน (จำนวน column = `templateRow3.length`) `cleanCellValue` ลบเครื่องหมาย single quote ออกจากทุก cell (`'` ห้ามมีใน output format)
4. `runOutputVerification` — สแกน output ที่ generate แล้วซ้ำอีกรอบทีละบรรทัด หา single quote ที่หลงเหลือและจำนวน pipe ที่ไม่ตรงกับ column count ที่คาดไว้ ได้เป็น `state.outputIssues` รันอัตโนมัติทุกครั้งหลัง conversion ไม่ใช่ manual step แยก
5. `updateOverallStatus` คุมปุ่ม Export ให้กดไม่ได้ถ้ามีไฟล์ไหน `status === 'error'` หรือเจอ output issues

Tab Template Settings (`initSettingsPanel`) ให้ override `templateRow1`/`templateRow3` ได้ทั้งพิมพ์ column name คั่นด้วย comma/newline หรืออัปโหลดไฟล์ Excel อ้างอิง (`handleTemplateExcelFile`) ที่จะดึงแถว 1 และแถว 3 มาใช้เป็น template ใหม่ตรงๆ เปลี่ยน template แล้วจะรัน `processUploadedFiles` ใหม่กับไฟล์ที่อัปโหลดไว้แล้วทันที

### Export

`exportTextFile` ดาวน์โหลด `state.outputText` เป็น `register_qrapiv2_{partnerId}_{yyyyMMdd}.txt` ผ่าน Blob + `<a download>` ชั่วคราว โดยใช้ค่าจาก Partner ID input และ File Date input ปัจจุบันมาสร้างชื่อไฟล์

### Deploy to SFTP (Step 3)

ปุ่ม "Generate Deploy Script" สร้างไฟล์ `.sh` ที่ scp ไฟล์ผลลัพธ์ + โลโก้ (ดาวน์โหลดจาก
`raw.githubusercontent.com/natingkaninantanaxyt-web/front-automation-hub/main/assets/...` ถ้ายังไม่มีอยู่ที่ bastion)
ขึ้น bastion (ถังกลาง) ก่อนเสมอ แล้วค่อยถามยืนยัน 2 ชั้น (`GO-LIVE` + `PROD`) ก่อน sftp เข้าโฟลเดอร์จริงของพาร์ตเนอร์
(`CJMART_KPAY_REGISAPI_INBOUND`) สคริปต์รันบนเครื่องผู้ใช้เอง (ต้องมี `gcloud` CLI login ไว้แล้ว) ไม่ใช่บนเว็บ

สำหรับคู่มือ git/GitHub/GitHub Pages แบบละเอียด (setup repo, commit, push, deploy) ดูที่
[README.md ของ Hub](../README.md)
