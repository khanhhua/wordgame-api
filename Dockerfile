FROM python:3.7-slim
ENV DB_HOST=mysql \
    DB_PORT=3306 \
    DB_USER=root \
    DB_PASSWORD=ILkopTAD2ut2exVEJUh5UjehL@f \
    JWT_SECRET=s3cr3t \
    RECAPTCHA_SECRET=s3cr3t

WORKDIR /app
COPY . .

RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

EXPOSE 8080
CMD python wsgi.py