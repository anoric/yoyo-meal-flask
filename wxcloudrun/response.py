import json

from flask import Response


def make_succ_empty_response():
    data = json.dumps({'code': 0, 'data': {}})
    return Response(data, mimetype='application/json')


def make_succ_response(data):
    data = json.dumps({'code': 0, 'data': data})
    return Response(data, mimetype='application/json')


def make_err_response(err_msg, code=-1, error_code=None):
    result = {'code': code, 'errorMsg': err_msg}
    if error_code:
        result['errorCode'] = error_code
    data = json.dumps(result)
    return Response(data, mimetype='application/json')
