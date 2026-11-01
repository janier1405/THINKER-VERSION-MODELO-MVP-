import pytest
from clinical.algorithms.news2.calculator import ConsciousnessLevel as C, NEWS2Calculator as N, VitalSigns, RULES_STATUS

def vs(**o):
    d = dict(respiratory_rate=16, oxygen_saturation=97, supplemental_oxygen=False, spo2_scale_2=False, systolic_bp=120,
             heart_rate=78, consciousness=C.ALERT, temperature=36.8); d.update(o); return VitalSigns(**d)

@pytest.mark.parametrize("v,s", [(8,3),(9,1),(11,1),(12,0),(20,0),(21,2),(24,2),(25,3)])
def test_respiratory_rate(v, s): assert N._score_respiratory_rate(v) == s
@pytest.mark.parametrize("v,s", [(91,3),(92,2),(93,2),(94,1),(95,1),(96,0)])
def test_spo2_scale1(v, s): assert N._score_oxygen_sat(v, False, False) == s
@pytest.mark.parametrize("v,o,s", [(83,False,3),(84,False,2),(85,True,2),(86,False,1),(87,True,1),(88,False,0),(92,True,0),
                                   (93,False,0),(99,False,0),(93,True,1),(94,True,1),(95,True,2),(96,True,2),(97,True,3)])
def test_spo2_scale2(v, o, s): assert N._score_oxygen_sat(v, True, o) == s
def test_supplemental_oxygen(): assert N._score_supplemental_oxygen(True) == 2 and N._score_supplemental_oxygen(False) == 0
@pytest.mark.parametrize("v,s", [(90,3),(91,2),(100,2),(101,1),(110,1),(111,0),(219,0),(220,3)])
def test_systolic(v, s): assert N._score_systolic_bp(v) == s
@pytest.mark.parametrize("v,s", [(40,3),(41,1),(50,1),(51,0),(90,0),(91,1),(110,1),(111,2),(130,2),(131,3)])
def test_heart_rate(v, s): assert N._score_heart_rate(v) == s
@pytest.mark.parametrize("c,s", [(C.ALERT,0),(C.NEW_CONFUSION,3),(C.VERBAL,3),(C.PAIN,3),(C.UNRESPONSIVE,3)])
def test_consciousness(c, s): assert N._score_consciousness(c) == s
@pytest.mark.parametrize("v,s", [(35.0,3),(35.1,1),(36.0,1),(36.1,0),(38.0,0),(38.1,1),(39.0,1),(39.1,2),(36.04,1),(36.06,0)])
def test_temperature(v, s): assert N._score_temperature(v) == s

def test_bands_and_status():
    assert N.evaluate(vs()).clinical_risk == "Bajo" and N.evaluate(vs()).rules_status == RULES_STATUS
    assert N.evaluate(vs(heart_rate=95, temperature=38.5)).clinical_risk == "Bajo"          # total 2
    r = N.evaluate(vs(respiratory_rate=8)); assert (r.total_score, r.clinical_risk) == (3, "Bajo-Medio")
    assert N.evaluate(vs(respiratory_rate=22, heart_rate=95, temperature=38.5, systolic_bp=105)).clinical_risk == "Medio"  # 5
    assert N.evaluate(vs(respiratory_rate=6, heart_rate=140, systolic_bp=80)).clinical_risk == "Alto"
def test_oxygen_adds_two(): assert N.evaluate(vs(supplemental_oxygen=True)).total_score == 2
