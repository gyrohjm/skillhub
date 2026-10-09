from test_task_mode_20260910 import research_design_with_unvalidated_values
import computation_design as cd


def test_task_user_override_does_not_inherit_validated_precision():
    design=research_design_with_unvalidated_values()
    design['design_mode']='task'
    entry=design['engine_stage_envelopes'][0]['parameter_selection']['basis_cutoff']
    entry['status']='validated'
    revised=cd.apply_engine_parameter_overrides(design,'M1',{'ENCUT':650})
    changed=revised['engine_stage_envelopes'][0]['parameter_selection']['basis_cutoff']
    assert changed['status']=='user_specified'
    assert changed['selected_value']==650
    assert changed['previous_selection']['status']=='validated'
    assert entry['status']=='validated'


def test_research_override_preserves_old_validation_as_history_only():
    design=research_design_with_unvalidated_values()
    entry=design['engine_stage_envelopes'][0]['parameter_selection']['basis_cutoff']
    entry['status']='validated'
    changed=cd.apply_engine_parameter_overrides(design,'M1',{'ENCUT':650})['engine_stage_envelopes'][0]['parameter_selection']['basis_cutoff']
    assert changed['status']=='candidate'
    assert changed['previous_selection']['status']=='validated'
