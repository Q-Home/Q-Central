FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY qbox_agent ./qbox_agent
CMD ["python", "-m", "qbox_agent"]
