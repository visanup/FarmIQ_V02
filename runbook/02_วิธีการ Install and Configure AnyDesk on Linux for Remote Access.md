# วิธีการ Install and Configure AnyDesk on Linux for Remote Access

คู่มือนี้สำหรับ **Ubuntu 24.04 LTS + Intel/AMD 64-bit (amd64)** และตั้งค่าให้สามารถ Remote เข้าเครื่อง Linux ได้โดย **ไม่ต้องมีคนที่เครื่องปลายทางกด Accept ทุกครั้ง (Unattended Access)**

> **สำคัญ:** สำหรับเครื่อง Intel ให้ใช้แพ็กเกจ **amd64 / x86_64** ไม่ใช่ `arm64`

---

## 1. ตรวจสอบ Architecture ของเครื่อง

เปิด Terminal แล้วรัน:

```bash
uname -m
```

ถ้าได้:

```text
x86_64
```

ให้ใช้ AnyDesk เวอร์ชัน:

```text
amd64
```

ถ้าได้:

```text
aarch64
```

หรือ

```text
arm64
```

จึงใช้เวอร์ชัน ARM64

---

## 2. ดาวน์โหลด AnyDesk

ดาวน์โหลด AnyDesk สำหรับ Linux จากเว็บไซต์ทางการ: (https://anydesk.com/en/downloads/linux)

**Linux → Ubuntu / Debian → 64-bit / amd64 → `.deb`**

ตัวอย่างชื่อไฟล์:

```text
anydesk_x.x.x-1_amd64.deb
```

หลังดาวน์โหลดแล้ว โดยทั่วไปไฟล์จะอยู่ที่:

```bash
~/Downloads
```

ตรวจสอบ:

```bash
ls ~/Downloads | grep anydesk
```

---

## 3. ติดตั้ง AnyDesk

เข้า Downloads:

```bash
cd ~/Downloads
```

ตรวจสอบไฟล์:

```bash
ls -lh anydesk*.deb
```

จากนั้นติดตั้ง:

```bash
sudo apt install ./anydesk*.deb
```

ถ้ามีคำถาม:

```text
Do you want to continue? [Y/n]
```

ให้กด:

```text
Y
```

แล้ว Enter

---

## 4. ตรวจสอบว่าติดตั้งสำเร็จ

ตรวจสอบ version:

```bash
anydesk --version
```

ตรวจสอบ Service:

```bash
systemctl status anydesk
```

ควรเห็นสถานะประมาณ:

```text
Active: active (running)
```

กด:

```text
q
```

เพื่อออกจากหน้า Status

ถ้า Service ยังไม่ทำงาน:

```bash
sudo systemctl enable --now anydesk
```

ตรวจสอบอีกครั้ง:

```bash
systemctl status anydesk
```

---

## 5. เปิด AnyDesk

สามารถเปิดจาก Ubuntu Application Menu แล้วค้นหา:

```text
AnyDesk
```

หรือเปิดจาก Terminal:

```bash
anydesk
```

เมื่อเปิดแล้ว จะเห็น **AnyDesk Address / This Desk** เช่น:

```text
123 456 789
```

จดหมายเลขนี้ไว้ เพราะเป็นหมายเลขที่ใช้ Remote จากเครื่อง Windows

---

# 6. ตั้งค่า Unattended Access

ขั้นตอนนี้สำคัญสำหรับเครื่องที่ติดตั้งอยู่หน้างาน เพราะทำให้สามารถ Remote เข้าเครื่องได้โดย **ไม่ต้องมีคนกด Accept**

เปิด:

```text
AnyDesk
    ↓
Settings
    ↓
Access
```

หา:

```text
Unattended Access
```

เลือก:

```text
Set password for unattended access
```

ตั้ง Password ที่มีความแข็งแรง เช่นอย่างน้อย 12–16 ตัวอักษร ประกอบด้วยตัวพิมพ์ใหญ่ ตัวพิมพ์เล็ก ตัวเลข และอักขระพิเศษ

**ไม่ควรบันทึก Password ไว้ใน Source Code, Git หรือไฟล์ `.env` ที่ commit ขึ้น Repository**

---

# 7. ตั้ง Permission สำหรับ Remote

ใน:

```text
Settings
→ Access
```

ตรวจสอบ Permission Profile สำหรับ Unattended Access

สำหรับเครื่องที่ต้อง Remote ไปดูแลระบบ แนะนำอนุญาตอย่างน้อย:

- Keyboard and mouse
- Clipboard
- File Manager / File Transfer ถ้าจำเป็น
- Restart / Reboot
- Lock / Unlock Keyboard and Mouse ตามความเหมาะสม

Permission ที่ไม่จำเป็นต่อการดูแลระบบสามารถปิดเพื่อลดความเสี่ยงด้าน Security

---

# 8. ตั้ง AnyDesk ให้ทำงานหลัง Boot

รัน:

```bash
sudo systemctl enable anydesk
```

ตรวจสอบ:

```bash
systemctl is-enabled anydesk
```

ควรได้:

```text
enabled
```

ตรวจสอบ Service:

```bash
systemctl is-active anydesk
```

ควรได้:

```text
active
```

ดังนั้นเมื่อ Ubuntu Restart:

```text
Ubuntu Boot
    ↓
Network Connected
    ↓
AnyDesk Service Start
    ↓
พร้อม Remote
```

โดยไม่จำเป็นต้องเปิดโปรแกรม AnyDesk ด้วยมือทุกครั้ง

---

# 9. ตรวจสอบ Internet

AnyDesk ต้องสามารถออก Internet ได้

ทดสอบ:

```bash
ping -c 4 8.8.8.8
```

และ:

```bash
ping -c 4 google.com
```

ถ้าทั้งสองทำงาน แสดงว่า Internet และ DNS โดยพื้นฐานใช้งานได้

ตรวจสอบ Default Route:

```bash
ip route
```

ควรมีบรรทัดประมาณ:

```text
default via 192.168.1.1 dev <network-interface>
```

---

# 10. Remote จาก Windows → Ubuntu

ที่เครื่อง Windows เปิด AnyDesk

ใส่:

```text
AnyDesk Address ของเครื่อง Ubuntu
```

แล้วกด:

```text
Connect
```

เมื่อถาม Password ให้ใส่:

```text
Unattended Access Password
```

สามารถเลือก:

```text
Log in automatically from now on
```

หรือบันทึก Password เฉพาะบนเครื่อง Admin ที่เชื่อถือได้

หลังจากนั้น Windows จะสามารถ Remote เข้า Ubuntu โดยไม่ต้องมีคนที่ Ubuntu กด Accept

---

# 11. ทดสอบ Reboot ก่อนนำเครื่องไปติดตั้งหน้างาน

ขั้นตอนนี้ **ควรทำก่อนนำเครื่องไป Farm / Factory**

Restart Ubuntu:

```bash
sudo reboot
```

รอเครื่อง Boot กลับมา แล้วจาก Windows ทดลอง Remote ด้วย AnyDesk ใหม่

ต้องสามารถเข้าได้โดย:

```text
Ubuntu Boot
      ↓
Internet Connected
      ↓
AnyDesk Service Started
      ↓
Windows → AnyDesk
      ↓
Password
      ↓
Remote เข้าได้
```

ถ้าทำได้ ถือว่า **Unattended Remote Access ผ่านการทดสอบ**

---

# 12. คำสั่ง Troubleshooting ที่ควรเก็บไว้

### ตรวจ AnyDesk

```bash
systemctl status anydesk
```

### Restart AnyDesk

```bash
sudo systemctl restart anydesk
```

### ตรวจ Auto Start

```bash
systemctl is-enabled anydesk
```

### ตรวจว่า Service ทำงานหรือไม่

```bash
systemctl is-active anydesk
```

### ดู Log

```bash
journalctl -u anydesk --no-pager -n 100
```

### ตรวจ IP

```bash
ip addr
```

### ตรวจ Routing

```bash
ip route
```

### ตรวจ Internet

```bash
ping -c 4 8.8.8.8
```

### ตรวจ DNS

```bash
ping -c 4 google.com
```

---

# 13. Checklist ก่อนนำเครื่องไปติดตั้งจริง

- [ ] Ubuntu Boot ได้ปกติ
- [ ] ใช้ AnyDesk package ถูก Architecture (`amd64` สำหรับ Intel/AMD x86-64)
- [ ] AnyDesk ติดตั้งเรียบร้อย
- [ ] `anydesk.service` เป็น `active`
- [ ] `anydesk.service` เป็น `enabled`
- [ ] จด AnyDesk Address แล้ว
- [ ] ตั้ง Unattended Access Password แล้ว
- [ ] ทดสอบ Remote จาก Windows แล้ว
- [ ] ทดสอบ Remote โดยไม่มีคนกด Accept แล้ว
- [ ] Restart Ubuntu แล้ว AnyDesk กลับมาเอง
- [ ] Internet กลับมาเองหลัง Restart
- [ ] Remote เข้าได้อีกครั้งหลัง Restart
- [ ] เก็บ Password ใน Password Manager หรือระบบ Credential ที่เหมาะสม
- [ ] ไม่เก็บ Password ใน Git / Source Code
- [ ] ทดสอบการ Remote จริงผ่าน Internet ไม่ใช่เฉพาะ LAN

---

## Architecture สำหรับการใช้งานหน้างาน

```text
                    Internet
                       │
                       │ 4G
                       ▼
               ┌──────────────┐
               │   4G Router  │
               └──────┬───────┘
                      │ LAN
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
 ┌─────────────────┐     ┌─────────────────┐
 │ IoT-Layer       │     │ Edge/Cloud-Layer│
 │ Ubuntu 24.04    │     │ Ubuntu 24.04    │
 │ AnyDesk         │     │ AnyDesk         │
 └─────────────────┘     └─────────────────┘
          ▲                       ▲
          │                       │
          └──────── Internet ─────┘
                      ▲
                      │
                AnyDesk Remote
                      │
               ┌──────────────┐
               │ Admin Windows│
               └──────────────┘
```

แนวทางนี้ทำให้เครื่อง Ubuntu ทั้ง **IoT-Layer** และ **Edge/Cloud-Layer** สามารถสื่อสารกันผ่าน LAN ภายในได้ตามปกติ ขณะเดียวกันใช้ Internet จาก 4G Router สำหรับ AnyDesk Remote Access ได้