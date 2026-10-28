"""Core transport dependencies only; no resource grants, health probes or writes."""
from three_mm_platform_wire import CONTRACT_VERSION, SCOPED_ACTIONS
from three_mm_protocol.application_requirements import assess_platform_requirements


class ApplicationRequirementsError(ValueError):
    def __init__(self, assessment):
        self.assessment = assessment
        identifiers = [item.requirement.requirement_id for item in assessment.requirements
                       if item.requirement.required and not item.supported]
        super().__init__('Required Core platform functions are unavailable: ' + ', '.join(identifiers))


def inspect_platform_requirements(definition):
    return assess_platform_requirements(definition.platform_requirements,
        transport_contract_version=CONTRACT_VERSION, operations=SCOPED_ACTIONS)


def require_platform_requirements(definition):
    assessment = inspect_platform_requirements(definition)
    if assessment.status == 'blocked':
        raise ApplicationRequirementsError(assessment)
    return assessment
