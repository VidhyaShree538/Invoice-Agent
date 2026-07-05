import requests

with open('uploads/0ef54e6266684723a9d72c1b18aa638e_sample_invoice.jpg', 'rb') as fh:
    files = {'file': ('sample_invoice.jpg', fh, 'image/jpeg')}
    r = requests.post('http://127.0.0.1:8000/api/invoices/upload', files=files, timeout=60)
    print(r.status_code)
    print(r.text)
