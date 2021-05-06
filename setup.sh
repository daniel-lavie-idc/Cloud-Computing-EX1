# debug
# set -o xtrace

REGION=$(aws ec2 describe-availability-zones | jq -r .AvailabilityZones[0].RegionName)
AWS_ACCOUNT=$(aws sts get-caller-identity  | jq -r .Account)
RUN_ID=$(date +'%N')
AWS_ROLE="lambda-role-$RUN_ID"
FUNC_NAME="my-func-$RUN_ID"
API_NAME="api-gateway-$RUN_ID"

echo "Creating role $AWS_ROLE..."
aws iam create-role --role-name $AWS_ROLE --assume-role-policy-document file://trust-policy.json

echo "Allowing writes to CloudWatch logs..."
aws iam attach-role-policy --role-name $AWS_ROLE  \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

DYNAMODB_TABLE_NAME="table-$RUN_ID"
echo "Creating dynamodb table"
aws dynamodb create-table \
    --table-name $DYNAMODB_TABLE_NAME \
    --attribute-definitions \
        AttributeName=ticketId,AttributeType=S \
    --key-schema AttributeName=ticketId,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=1,WriteCapacityUnits=1

echo "Allowing read and write permission to the dynamodb table..."
# Couldn't find a decent way to give access to specific operations, so give full access in order for the lambda to work
aws iam attach-role-policy --role-name $AWS_ROLE --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess 

echo "Packaging code..."
zip lambda.zip lambda_function.py

echo "Wait for role creation"

aws iam wait role-exists --role-name $AWS_ROLE
aws iam get-role --role-name $AWS_ROLE
ARN_ROLE=$(aws iam get-role --role-name $AWS_ROLE | jq -r .Role.Arn)

echo "Workaround consistency rules in AWS roles after creation... (sleep 10)"
sleep 10

echo "Creating function $FUNC_NAME..."
aws lambda create-function --function-name $FUNC_NAME \
    --zip-file fileb://lambda.zip --handler lambda_function.lambda_handler \
    --runtime python3.8 --role $ARN_ROLE

echo "Add dynamodb table name environment variable"
aws lambda update-function-configuration --function-name $FUNC_NAME \
    --environment "Variables={DYNAMO_TABLE_NAME=$DYNAMODB_TABLE_NAME}"

FUNC_ARN=$(aws lambda get-function --function-name $FUNC_NAME | jq -r .Configuration.FunctionArn)

echo "Creating API Gateway..."
API_CREATED=$(aws apigatewayv2 create-api --name $API_NAME --protocol-type HTTP --target $FUNC_ARN)
API_ID=$(echo $API_CREATED | jq -r .ApiId)
API_ENDPOINT=$(echo $API_CREATED | jq -r .ApiEndpoint)

STMT_ID=$(uuidgen)

aws lambda add-permission --function-name $FUNC_NAME \
    --statement-id $STMT_ID --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$AWS_ACCOUNT:$API_ID/*"

echo "The following http endpoints were created:"
echo "$API_ENDPOINT/entry"
echo "$API_ENDPOINT/exit"