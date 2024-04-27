FROM python:3
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt
COPY . /app
RUN chmod +x /app/start.sh
CMD ["./start.sh"]