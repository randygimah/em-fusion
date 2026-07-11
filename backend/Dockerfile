# an official lightweight Python runtime as the parent image
FROM python:3.11-slim

# Working directory
WORKDIR /app

# Environment variables to optimise python behaviour
# PYTHONDONTWRITEBYTECODE=1 prevents python from writing .pyc cache files to disk, saving space
# PYTHONUNBUFFERED ensures that console logs are printed instantly instead of buffering, making debugging easier
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy dependency file to current workdir to leverage docker cache
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of application code into container
COPY . .

# Expose the port that uvicorn run on
EXPOSE 8080

# Command to run the app using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]