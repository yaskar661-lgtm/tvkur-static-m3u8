from flask import Flask, Response, request
import re
import requests
import os

app = Flask(__name__)

# Orijinal istek için gereken header'lar
TARGET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://player.tvkur.com/",
    "Origin": "https://player.tvkur.com",
}

ORIGINAL_MASTER_URL = "https://content.tvkur.com/l/c7e1da7mm25p552d9u9g/master.m3u8"


@app.route("/master.m3u8")
def proxy_master():
  try:
    # Ana m3u8 dosyasını çek
    resp = requests.get(ORIGINAL_MASTER_URL, headers=TARGET_HEADERS, timeout=10)

    # Hata durumunda (4xx, 5xx) otomatik exception fırlatır
    resp.raise_for_status()

    playlist_content = resp.text
    base_url = re.sub(r"[^/]+$", "", ORIGINAL_MASTER_URL)
    host_root = request.host_url.rstrip("/")  # Örn: http://127.0.0.1:5000

    # İçindeki alt m3u8 bağlantılarını host + proxy ile yeniden yaz
    new_lines = []
    for line in playlist_content.splitlines():
      line = line.strip()
      if line and not line.startswith("#"):
        full_url = base_url + line
        proxied_url = f"{host_root}/proxy?url={full_url}"
        new_lines.append(proxied_url)
      else:
        new_lines.append(line)

    updated_playlist = "\n".join(new_lines)
    return Response(updated_playlist, mimetype="application/vnd.apple.mpegurl")

  except requests.exceptions.RequestException as e:
    return f"Master playlist alınırken hata oluştu: {str(e)}", 500
  except Exception as e:
    return str(e), 500


@app.route("/proxy")
def proxy_media():
  target_url = request.args.get("url")
  if not target_url:
    return "URL belirtilmedi", 400

  try:
    # Orijinal kaynaktan veriyi iste
    req = requests.get(
        target_url, headers=TARGET_HEADERS, stream=True, timeout=10
    )

    # HTTP hata kodlarını yakala
    req.raise_for_status()

    content_type = req.headers.get("Content-Type", "application/octet-stream")

    # Eğer gelen içerik alt m3u8 dosyası ise, segmentleri düzenle
    if (
        "application/vnd.apple.mpegurl" in content_type
        or "audio/mpegurl" in content_type
        or target_url.endswith(".m3u8")
    ):
      playlist_content = req.text
      base_url = re.sub(r"[^/]+$", "", target_url)
      host_root = request.host_url.rstrip("/")

      new_lines = []
      for line in playlist_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
          if line.startswith("http://") or line.startswith("https://"):
            segment_full_url = line
          else:
            segment_full_url = base_url + line

          proxied_segment_url = f"{host_root}/proxy?url={segment_full_url}"
          new_lines.append(proxied_segment_url)
        else:
          new_lines.append(line)

      updated_playlist = "\n".join(new_lines)
      return Response(updated_playlist, mimetype="application/vnd.apple.mpegurl")

    # .ts veya .m4s segmentlerini direkt stream et
    return Response(
        req.iter_content(chunk_size=1024),
        status=req.status_code,
        mimetype=content_type,
    )

  except requests.exceptions.RequestException as e:
    return f"Medya/Parça alınırken hata oluştu: {str(e)}", 500
  except Exception as e:
    return str(e), 500


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=5000, debug=True)
