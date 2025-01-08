# Business Integrity

## Local Development Setup

### **1. Prerequisites**
- Python 3.12 or higher
- Virtual environment with `venv`

### **2. Local Installation**
1. Clone the repository:
   ```bash
   git clone https://github.com/AInsteinsBR/BusinessIntegrity.git
   cd BusinessIntegrity
   ```

2. Create and activate the virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # For Linux/Mac
   venv\Scripts\activate  # For Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   - Copy `.env-example` to `.env` and fill in the required variables:
     ```bash
     cp env-example .env
     ```
   - Required API keys:
     - [Cohere API Key](https://cohere.com/) - For text generation models
     - [OpenAI API Key](https://openai.com/) - For AI capabilities
     - [Serper API Key](https://serper.dev/) - For Google search functionality
   - Database configuration (for local development):
     ```
     DB_HOST=localhost
     DB_USER=your_user
     DB_PASSWORD=your_password
     DB_NAME=businessintegrity
     ```

5. Create database tables:
    ```bash
    python3 config.py
    ```

6. Run the application:
   ```bash
   export FLASK_APP=app/app.py
   flask run
   ```

## AWS Deployment with SAM

### **1. Prerequisites**
- [AWS CLI](https://aws.amazon.com/cli/) installed and configured
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html) installed
- [Docker](https://www.docker.com/get-started/) installed locally (for testing the build)
- An AWS account with appropriate permissions
- All required API keys (Cohere, OpenAI, Serper)

### **2. Deployment Steps**

1. Configure your `.env` file with all required variables:
   ```plaintext
   COHERE_API_KEY=your_cohere_key
   OPENAI_API_KEY=your_openai_key
   SERPER_API_KEY=your_serper_key
   DB_USER=your_database_user
   DB_PASSWORD=your_secure_password
   DB_NAME=your_database_name
   ```

   Important notes about the database configuration:
   - DB_NAME and DB_USER must start with a letter and contain only alphanumeric characters
   - DB_PASSWORD must be at least 8 characters long and contain only alphanumeric characters
   - DB_HOST will be automatically configured during deployment

2. Make the deployment script executable:
   ```bash
   chmod +x deploy.sh
   ```

3. Run the deployment script:
   ```bash
   ./deploy.sh your-stack-name
   ```

   The script will:
   - Validate all environment variables
   - Check for required tools (AWS CLI, SAM CLI)
   - Test the Docker build locally
   - Deploy using AWS SAM with the following resources:
     - EC2 instance (t2.micro - Free Tier eligible)
     - RDS MySQL instance (db.t3.micro - Free Tier eligible)
     - VPC with public and private subnets
     - Required security groups and networking components

4. During deployment:
   - You'll be asked to confirm before proceeding
   - The script will display the instance types being used
   - You can monitor the deployment progress in real-time

5. After successful deployment, you'll receive:
   - The EC2 instance's public IP address
   - The RDS endpoint
   - An SSH private key file (`<stack-name>-key.pem`)
   - Instructions for connecting to your instance

### **3. Post-Deployment**

1. Access your application:
   ```
   http://<your-ec2-public-ip>
   ```

2. Connect to the EC2 instance:
   ```bash
   ssh -i <stack-name>-key.pem ec2-user@<your-ec2-public-ip>
   ```

3. View application logs:
   ```bash
   sudo journalctl -u flaskapp
   ```

4. Monitor the Docker container:
   ```bash
   docker ps
   docker logs business-analysis
   ```

### **4. Important Notes**

- The deployment uses AWS Free Tier eligible resources:
  - EC2: t2.micro
  - RDS: db.t3.micro
  - 20GB GP2 storage for RDS
- RDS creation takes approximately 10-15 minutes
- Monitor your AWS Free Tier usage to avoid unexpected charges
- The application runs as a Docker container with automatic restart
- Database backups are retained for 7 days
- The database is not publicly accessible (only from EC2)
- The deployment script includes safety checks for:
  - Required environment variables
  - Database name and user validation
  - Docker build testing
  - AWS and SAM CLI availability

### **5. Cleanup**

To avoid ongoing charges, delete the stack when no longer needed:
```bash
sam delete --stack-name your-stack-name
```

This will remove all created resources, including:
- EC2 instance
- RDS database
- VPC and associated networking components
- Security groups
- SSH key pair