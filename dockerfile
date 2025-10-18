FROM python:3.10-slim

WORKDIR /app
COPY app.py /app
RUN pip install flask requests

ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]