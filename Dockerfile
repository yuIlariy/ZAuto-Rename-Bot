# 1. Use the specific Python 3.11.9 slim image for stability
FROM python:3.11.9-slim

# 2. Set the working directory in the container
WORKDIR /app

# 3. Install FFmpeg (Crucial for metadata) and GCC (for compiling dependencies)
RUN apt-get update -qq && apt-get install -y ffmpeg gcc

# 4. Copy the dependencies file to the working directory
COPY requirements.txt .

# 5. Install any needed dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code to the working directory
COPY . .

# 7. Command to run the application
CMD ["python3", "bot.py"]
