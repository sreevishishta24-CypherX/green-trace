import requests, json
resp = requests.post('http://127.0.0.1:8000/detect', data={'bbox':'77.55,12.85,77.57,12.87','project_point':'77.563,12.859','buffers':'30,50,100','enable_ndwi':'true'})
print('status', resp.status_code)
print(json.dumps(resp.json(), indent=2))
