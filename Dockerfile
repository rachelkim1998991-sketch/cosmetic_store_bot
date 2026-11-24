FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Avval faqat talablar: kod o'zgarganda kutubxonalar qayta o'rnatilmaydi (kesh)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
COPY app ./app

# Root bo'lmagan foydalanuvchi
RUN useradd --create-home --uid 10001 botuser && chown -R botuser /app
USER botuser

# Render PORT o'zgaruvchisini o'zi beradi (odatda 10000); main.py shuni o'qiydi
EXPOSE 10000

CMD ["python", "main.py"]
