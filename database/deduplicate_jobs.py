# database/deduplicate_jobs.py
import sys
import os
import re

sys.stdout.reconfigure(encoding="utf-8")

# Đảm bảo import được từ root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.facebook_db import FacebookDB

def extract_correct_external_id(url: str) -> str:
    """Trích ID từ URL job. Lấy số từ 5 chữ số trở lên cuối cùng."""
    if not url:
        return ""
    matches = re.findall(r"\d{5,}", url)
    if matches:
        return matches[-1]
    return url[-50:]

def deduplicate():
    print("🚀 Bắt đầu quét và làm sạch dữ liệu trùng lặp trong Database...")
    
    with FacebookDB() as db:
        cursor = db.conn.cursor()
        
        # 1. Lấy toàn bộ các job hiện có để xử lý
        cursor.execute("SELECT id, source_name, external_id, source_url, title, company FROM jobs")
        rows = cursor.fetchall()
        print(f"📋 Tìm thấy {len(rows)} jobs trong Database.")
        
        # Mapping để phân tích trùng lặp
        # Khóa: (source_name, correct_external_id), Giá trị: list các row dict
        unique_groups = {}
        
        for r in rows:
            jid, source_name, ext_id, source_url, title, company = r
            
            # Chuẩn hóa source_name
            source = (source_name or "").lower().strip()
            
            # Trích xuất external_id chuẩn hóa
            correct_id = ext_id
            if source_url:
                correct_id = extract_correct_external_id(source_url)
            
            if not correct_id:
                correct_id = f"fallback_{jid}"
                
            key = (source, correct_id)
            
            job_dict = {
                "id": jid,
                "source_name": source,
                "external_id": ext_id,
                "correct_external_id": correct_id,
                "source_url": source_url,
                "title": title,
                "company": company
            }
            
            if key not in unique_groups:
                unique_groups[key] = []
            unique_groups[key].append(job_dict)
            
        # 2. Phân tích trùng lặp và xác định các id cần giữ / cần xóa
        ids_to_delete = []
        updates_to_make = [] # list of (id, correct_external_id)
        
        duplicates_count = 0
        
        for key, group in unique_groups.items():
            # Sắp xếp theo ID tăng dần (giữ lại job được crawl đầu tiên)
            group.sort(key=lambda x: x["id"])
            
            # Phần tử đầu tiên là gốc
            keep_job = group[0]
            
            # Nếu external_id hiện tại khác với correct_external_id, đánh dấu để update
            if keep_job["external_id"] != keep_job["correct_external_id"]:
                updates_to_make.append((keep_job["id"], keep_job["correct_external_id"]))
                
            # Các phần tử còn lại là trùng lặp
            if len(group) > 1:
                duplicates_count += len(group) - 1
                for dup in group[1:]:
                    ids_to_delete.append(dup["id"])
                    print(f"  ❌ Phát hiện trùng lặp: ID {dup['id']} -> Trùng với gốc ID {keep_job['id']} "
                          f"({keep_job['title'][:30]} | {keep_job['company'][:20]})")
                    
        print(f"\n📊 Kết quả phân tích:")
        print(f"  - Số lượng bài trùng lặp cần xóa: {duplicates_count}")
        print(f"  - Số lượng bài cần cập nhật external_id: {len(updates_to_make)}")
        
        # 3. Tiến hành xóa các bài trùng lặp trước
        if ids_to_delete:
            print("\n🗑️  Đang tiến hành xóa các bài trùng lặp...")
            # Xóa theo lô để tránh tràn câu lệnh SQL
            batch_size = 100
            for i in range(0, len(ids_to_delete), batch_size):
                batch = ids_to_delete[i:i+batch_size]
                placeholders = ",".join(["?"] * len(batch))
                cursor.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", batch)
                db.conn.commit()
            print(f"  ✅ Đã xóa thành công {len(ids_to_delete)} bài trùng lặp từ Database.")
            
        # 4. Cập nhật correct external_id cho các bài giữ lại
        if updates_to_make:
            print("\n🔄 Đang cập nhật external_id chuẩn hóa cho các bài giữ lại...")
            for jid, correct_id in updates_to_make:
                try:
                    cursor.execute("UPDATE jobs SET external_id = ? WHERE id = ?", (correct_id, jid))
                    db.conn.commit()
                except Exception as e:
                    print(f"  ⚠️ Không thể cập nhật ID {jid} thành {correct_id}: {e}")
            print("  ✅ Đã cập nhật xong external_id.")
            
        print("\n🎉 HOÀN TẤT DỌN DẸP TRÙNG LẶP DATABASE!")

if __name__ == "__main__":
    deduplicate()
