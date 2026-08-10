"""동영상에서 화재(불꽃/연기)를 검출해 백엔드로 넘기는 파이프라인.

- detector      프레임 → 검출 목록 (YOLO 만 안다)
- video_source  영상 파일 → 프레임 (OpenCV 만 안다)
- sender        검출 목록 → 백엔드 (HTTP 만 안다)

셋을 엮는 건 run_video.py 하나뿐이다.
"""
