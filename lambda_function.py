import datetime
import json
import math
import os
import random
import string

import boto3
from boto3.dynamodb.conditions import Key

ENTRY_ENDPOINT = 'entry'
EXIT_ENDPOINT = 'exit'

TICKET_ID = 'ticketId'
TICKET_ID_LENGTH = 6
PLATE = 'plate'
PARKING_LOT = 'parkingLot'
QUERY_STRING_PARAMETERS = 'queryStringParameters'

DYNAMODB_TABLE_NAME = os.environ.get('DYNAMO_TABLE_NAME')

PRICE_PER_HOUR_DOLLAR = 10
PRICE_PER_15_MINUTES_DOLLAR = PRICE_PER_HOUR_DOLLAR / 4


def lambda_handler(event, context):
    if QUERY_STRING_PARAMETERS not in event.keys():
        return create_bad_response('At least one parameter is needed for all api calls')
    query_string_parameters = event[QUERY_STRING_PARAMETERS]
    raw_path = event['rawPath']
    if raw_path.endswith(ENTRY_ENDPOINT):
        return handle_entry(query_string_parameters)
    elif raw_path.endswith(EXIT_ENDPOINT):
        return handle_exit(query_string_parameters)
    else:
        return create_bad_response('wrong endpoint')


def handle_entry(query_string_parameters):
    print("entry endpoint was called")
    if PLATE not in query_string_parameters.keys() or PARKING_LOT not in query_string_parameters.keys():
        return create_bad_response('One of the following parameters are missing: {}, {}'.format(PLATE, PARKING_LOT))
    plate = query_string_parameters[PLATE]
    parking_lot = query_string_parameters[PARKING_LOT]
    current_posix_time = datetime.datetime.now().timestamp()
    ticket_id = ''.join(random.choice(string.digits) for i in range(TICKET_ID_LENGTH))
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    table.put_item(
        Item={
            'ticketId': ticket_id,
            'parkingLot': parking_lot,
            'parkingPosixTime': int(current_posix_time),
            'plate': plate
        }
    )
    return {
        'statusCode': 200,
        'body': json.dumps('ticket id: {}'.format(ticket_id))
    }


def handle_exit(query_string_parameters):
    print("exit endpoint was called")
    if TICKET_ID not in query_string_parameters.keys():
        return create_bad_response('{} parameter is missing'.format(TICKET_ID))
    ticket_id = query_string_parameters[TICKET_ID]

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    query_result = table.query(KeyConditionExpression=Key('ticketId').eq(ticket_id))
    table_entries = query_result['Items']
    if len(table_entries) == 0:
        return create_bad_response('Wrong ticketId was given')
    table_entry = table_entries[0]
    plate = table_entry['plate']
    parking_posix_time = table_entry['parkingPosixTime']
    parked_time_delta = datetime.datetime.fromtimestamp(
        datetime.datetime.now().timestamp()) - datetime.datetime.fromtimestamp(parking_posix_time)
    parked_seconds = parked_time_delta.seconds
    parked_minutes = math.floor(parked_seconds / 60)
    # We add additional PRICE_PER_15_MINUTES_DOLLAR to the charge for the current 15 minutes slot,
    # even if they did not end yet.
    parking_charge = (math.floor(parked_minutes / 15) * PRICE_PER_15_MINUTES_DOLLAR) + PRICE_PER_15_MINUTES_DOLLAR
    parking_lot = table_entry['parkingLot']

    # All good
    return {
        'statusCode': 200,
        'body': json.dumps('Amount to pay: {}$'.format(parking_charge))
    }


def create_bad_response(message):
    return {
        'statusCode': 404,
        'body': json.dumps(message)
    }
