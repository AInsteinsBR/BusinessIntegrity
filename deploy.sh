#!/bin/bash

# Check if stack name is provided
if [ -z "$1" ]; then
    echo "Please provide a stack name"
    echo "Usage: ./deploy.sh <stack-name>"
    exit 1
fi

STACK_NAME=$1
KEY_FILE="${STACK_NAME}-key.pem"

# Function to validate database name
validate_db_name() {
    local db_name=$1
    if [[ ! $db_name =~ ^[a-zA-Z][a-zA-Z0-9]*$ ]]; then
        return 1
    fi
    return 0
}

# Function to validate database user
validate_db_user() {
    local db_user=$1
    if [[ ! $db_user =~ ^[a-zA-Z][a-zA-Z0-9]*$ ]]; then
        return 1
    fi
    return 0
}

# Function to prompt for a variable if not set
prompt_var() {
    local var_name=$1
    local prompt_text=$2
    local is_secret=$3

    while true; do
        if [ "$is_secret" = "true" ]; then
            read -s -p "$prompt_text: " value
            echo
        else
            read -p "$prompt_text: " value
        fi

        case $var_name in
            "DB_NAME")
                if validate_db_name "$value"; then
                    break
                else
                    echo "Database name must start with a letter and contain only alphanumeric characters (no underscores or special characters)"
                fi
                ;;
            "DB_USER")
                if validate_db_user "$value"; then
                    break
                else
                    echo "Database user must start with a letter and contain only alphanumeric characters (no underscores or special characters)"
                fi
                ;;
            "DB_PASSWORD")
                if [[ ${#value} -ge 8 && "$value" =~ ^[a-zA-Z0-9]+$ ]]; then
                    break
                else
                    echo "Password must be at least 8 characters and contain only alphanumeric characters"
                fi
                ;;
            *)
                break
                ;;
        esac
    done

    eval "$var_name='$value'"
}

# Check for AWS CLI and SAM CLI
if ! command -v aws &> /dev/null; then
    echo "AWS CLI is not installed. Please install it first."
    exit 1
fi

if ! command -v sam &> /dev/null; then
    echo "SAM CLI is not installed. Please install it first."
    exit 1
fi

# Prompt for environment variables if not set
prompt_var "COHERE_API_KEY" "Enter Cohere API Key" true
prompt_var "OPENAI_API_KEY" "Enter OpenAI API Key" true
prompt_var "SERPER_API_KEY" "Enter Serper API Key" true

# Prompt for database configuration
echo "Database Configuration:"
prompt_var "DB_NAME" "Enter Database Name (alphanumeric only, must start with a letter)" false
prompt_var "DB_USER" "Enter Database User (alphanumeric only, must start with a letter)" false
prompt_var "DB_PASSWORD" "Enter Database Password (min 8 characters, alphanumeric only)" true

# Set instance types for free tier
DB_INSTANCE_CLASS="db.t2.micro"
INSTANCE_TYPE="t2.micro"

echo "Using free tier eligible instances:"
echo "- EC2: $INSTANCE_TYPE"
echo "- RDS: $DB_INSTANCE_CLASS"
echo "Database Name: $DB_NAME"
echo "Database User: $DB_USER"

# Confirm deployment
read -p "Do you want to proceed with the deployment? (y/n): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 1
fi

# Deploy the stack
echo "Deploying stack ${STACK_NAME}..."
sam deploy \
  --template-file template.yaml \
  --stack-name $STACK_NAME \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    InstanceType="$INSTANCE_TYPE" \
    CohereApiKey="$COHERE_API_KEY" \
    OpenAIApiKey="$OPENAI_API_KEY" \
    SerperApiKey="$SERPER_API_KEY" \
    DBUser="$DB_USER" \
    DBPassword="$DB_PASSWORD" \
    DBName="$DB_NAME" \
    DBInstanceClass="$DB_INSTANCE_CLASS"

# Check if deployment was successful
if [ $? -ne 0 ]; then
    echo "Deployment failed!"
    exit 1
fi

# Wait for stack creation to complete
echo "Waiting for stack creation to complete..."
if ! aws cloudformation wait stack-create-complete --stack-name $STACK_NAME; then
    echo "Stack creation failed or timed out"
    exit 1
fi

# Get stack outputs
echo "Getting stack outputs..."
INSTANCE_IP=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs[?OutputKey==`PublicIP`].OutputValue' --output text)
RDS_ENDPOINT=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs[?OutputKey==`RDSEndpoint`].OutputValue' --output text)

# Get and save the private key
echo "Retrieving and saving the private key..."
if aws ec2 describe-key-pairs --key-names "${STACK_NAME}-key" &>/dev/null; then
    aws ssm get-parameter \
        --name "/ec2/keypair/$(aws ec2 describe-key-pairs --key-names "${STACK_NAME}-key" --query 'KeyPairs[0].KeyPairId' --output text)" \
        --with-decryption \
        --query 'Parameter.Value' \
        --output text > "$KEY_FILE"

    # Set correct permissions for the key file
    chmod 400 "$KEY_FILE"
else
    echo "Warning: Key pair not found"
fi

echo "Deployment complete!"
if [ -f "$KEY_FILE" ]; then
    echo "Your private key has been saved to: $KEY_FILE"
fi
if [ ! -z "$INSTANCE_IP" ]; then
    echo "Instance Public IP: $INSTANCE_IP"
    echo "To connect to your instance:"
    echo "ssh -i $KEY_FILE ec2-user@$INSTANCE_IP"
fi
if [ ! -z "$RDS_ENDPOINT" ]; then
    echo "RDS Endpoint: $RDS_ENDPOINT"
fi

echo ""
echo "Important notes:"
echo "1. The RDS database may take 10-15 minutes to be created and available"
echo "2. Both EC2 and RDS instances are using free tier eligible types"
echo "3. Monitor your AWS Free Tier usage to avoid unexpected charges"
echo "4. The Flask application will be automatically started as a system service"
echo "5. To view application logs: ssh into the instance and run 'journalctl -u flaskapp'"