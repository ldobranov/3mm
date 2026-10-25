class Service:
    def handle(self, operation_id, payload, context):
        if operation_id == 'health' and context.audience == 'internal':
            return {'status':'ready'}
        raise ValueError('Unknown probe operation')

def create_service(application):
    return Service()
