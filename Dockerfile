FROM ghcr.io/ciromattia/kcc:latest

WORKDIR /smtp

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY ./smtp.py .

ENTRYPOINT ["/smtp/smtp.py"]