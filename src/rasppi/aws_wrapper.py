import boto3
from botocore.exceptions import  ClientError
import logging
from json import loads, dumps
from typing import List, Any, Dict, Callable,Tuple, Iterable
from uuid import uuid4
from datetime import datetime
logger = logging.getLogger("aws")

#AwsConfig = Config.RawConfig['aws']
logging.getLogger('botocore').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

def getClient(awsconfig):
    #if awsconfig['use_system_credentials']:
    #    return boto3.client('sqs')
    #else:
        return boto3.client('sqs', aws_access_key_id=awsconfig['key_id'], aws_secret_access_key=awsconfig['access_key'],
                 region_name=awsconfig['region'])

def read_queue(awsconfig, callback = None):
    maxMessages = 10 #0-10, limited by AWS

    sqs = getClient(awsconfig)

    fullQueue = True
    totalRead = 0
    now = datetime.now()
    while fullQueue:
        if (datetime.now() - now).total_seconds() > 45: #don't stay in this loop for too long
            break
        response = sqs.receive_message(QueueUrl=awsconfig['incoming'], AttributeNames=['SentTimestamp'],
                                       MaxNumberOfMessages=maxMessages,
                                       MessageAttributeNames=['All'],
                                        VisibilityTimeout=20,
                                        WaitTimeSeconds=5)
        if 'Messages' in response:
            numMessages = len(response['Messages'])
            if numMessages < maxMessages:
                fullQueue = False
            for m in response['Messages']:
                if callback is not None:
                    try:
                        bodyjson = loads(m['Body'])
                    except Exception as lse:
                        escaped = m['Body'].replace("\n","\\n")
                        logging.error(f"Got an invalid SQS message! Deleting it. Message: {escaped}. Stack trace: {lse}")
                        sqs.delete_message(QueueUrl=awsconfig['incoming'], ReceiptHandle=m['ReceiptHandle'])
                        continue
                    try:
                        clearIt = callback(bodyjson)
                    except Exception as cbe:
                        escaped = m['Body'].replace("\n", "\\n")
                        logging.error(f"Failure calling message callback on SQS queue. Message: {escaped}. Stack trace: {cbe}")
                        sqs.delete_message(QueueUrl=awsconfig['incoming'], ReceiptHandle=m['ReceiptHandle'])
                        continue
                    if clearIt:
                        sqs.delete_message(QueueUrl=awsconfig['incoming'], ReceiptHandle=m['ReceiptHandle'])
                else:
                    logging.warning(f'Got SQS Message With No Callback!: {m["Body"]}')
            totalRead += numMessages

        else:
            fullQueue = False

    if totalRead > 0:
        logger.debug(f"Read {len(response['Messages'])} message(s) from queue!")
    else:
        logging.debug("No messages in response")

def write_queue(messages: Iterable[Tuple[Any, Any]], awsconfig) -> Tuple[List[Any],List[Any]]:
    if Callable is None:
        return
    sqs = getClient(awsconfig)

    succeeded = []
    failed = []
    for (item, mapping) in messages:
        try:
            sqs.send_message(QueueUrl=awsconfig['outgoing'],
                         MessageBody=dumps(mapping),
                         MessageGroupId='hostname', #TODO
                         MessageDeduplicationId=str(uuid4()))
            succeeded.append(item)
        except ClientError as clienterror:
            logging.error(f"Failed to send message: {clienterror}")
            failed.append(item)
        except Exception as ex:
            logging.warning(f"Failed to send messages: {ex}")
            failed.append(item)
            pass
    return (succeeded,failed)

def TestAws(awsconfig : Dict[str,str]):
    sqs = boto3.client('sqs', aws_access_key_id=awsconfig['key_id'], aws_secret_access_key=awsconfig['access_key'],
                       region_name=awsconfig['region'])

    response = sqs.receive_message(QueueUrl=awsconfig['incoming'], AttributeNames=['SentTimestamp'],
                                   MaxNumberOfMessages=1,
                                   MessageAttributeNames=['All'],
                                   VisibilityTimeout=5,
                                   WaitTimeSeconds=1)
    response = sqs.receive_message(QueueUrl=awsconfig['outgoing'], AttributeNames=['SentTimestamp'],
                                       MaxNumberOfMessages=1,
                                       MessageAttributeNames=['All'],
                                       VisibilityTimeout=5,
                                       WaitTimeSeconds=1)

#def cb(body):
#    print(body)
#    pass

#read_queue(callback=cb)
#write_queue([{"a":"b"}])