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
- An AWS account with appropriate permissions
- All required API keys (Cohere, OpenAI, Serper)

### **2. Deployment Steps**

1. Configure your `.env` file with the required API keys and database settings:
   ```
   COHERE_API_KEY=your_cohere_key
   OPENAI_API_KEY=your_openai_key
   SERPER_API_KEY=your_serper_key
   DB_USER=admin
   DB_PASSWORD=your_secure_password
   DB_NAME=businessintegrity
   ```

   Note: DB_HOST will be automatically configured during deployment.

2. Make the deployment script executable:
   ```bash
   chmod +x deploy.sh
   ```

3. Deploy the application:
   ```bash
   ./deploy.sh your-stack-name
   ```

   The deployment script will:
   - Validate your environment variables
   - Create a VPC with public and private subnets
   - Deploy an EC2 instance (t2.micro - Free Tier eligible)
   - Deploy an RDS MySQL instance (db.t3.micro - Free Tier eligible)
   - Configure security groups and networking
   - Set up the application as a systemd service

4. After deployment, you'll receive:
   - The public IP of your EC2 instance
   - The RDS endpoint
   - SSH key file for EC2 access
   - Instructions for connecting to your instance

### **3. Post-Deployment**

1. Access your application:
   ```
   http://<your-ec2-public-ip>
   ```

2. SSH into the EC2 instance:
   ```bash
   ssh -i <stack-name>-key.pem ec2-user@<your-ec2-public-ip>
   ```

3. View application logs:
   ```bash
   sudo journalctl -u flaskapp
   ```

### **4. Important Notes**

- The deployment uses AWS Free Tier eligible resources:
  - EC2: t2.micro
  - RDS: db.t3.micro
  - 20GB GP2 storage for RDS
- RDS creation takes approximately 10-15 minutes
- Monitor your AWS Free Tier usage to avoid unexpected charges
- The application runs as a systemd service for automatic startup
- Database backups are retained for 7 days
- The database is not publicly accessible (only from EC2)

### **5. Cleanup**

To avoid ongoing charges, delete the stack when no longer needed:
```bash
aws cloudformation delete-stack --stack-name your-stack-name