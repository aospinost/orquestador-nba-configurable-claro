import numpy as np
import pandas as pd
import pytest

from engine import data_loader
from engine.config_store import Condition
from engine.expressions import EvalContext, ExpressionError, check_condition, evaluate, evaluate_all

RAW = pd.DataFrame({
    "id_cliente": ["a", "b", "c", "d"],
    "edad": ["20", "35", "50", "65"],
    "cal": ["E", "A", "C", "P"],
    "lista": ["X|Y", "", "Y", "Z"],
    "flag": ["1", "0", "1", "0"],
})


@pytest.fixture
def df():
    return data_loader.coerce(RAW)


def ev(df, a, op, v, product=None, consts=None):
    return evaluate(Condition(a, op, v), EvalContext(df, consts or {}, 0, product)).tolist()


def test_numeric_ops(df):
    assert ev(df, "edad", "<", "35") == [True, False, False, False]
    assert ev(df, "edad", "<=", "35") == [True, True, False, False]
    assert ev(df, "edad", ">", "50") == [False, False, False, True]
    assert ev(df, "edad", ">=", "50") == [False, False, True, True]
    assert ev(df, "edad", "==", "50") == [False, False, True, False]
    assert ev(df, "edad", "!=", "50") == [True, True, False, True]
    assert ev(df, "edad", "en", "20|65") == [True, False, False, True]
    assert ev(df, "edad", "no_en", "20|65") == [False, True, True, False]
    assert ev(df, "flag", "==", "sí") == [True, False, True, False]


def test_text_ops(df):
    assert ev(df, "cal", "en", "C|P") == [False, False, True, True]
    assert ev(df, "cal", "no_en", "E|A|B") == [False, False, True, True]
    assert ev(df, "cal", "==", "E") == [True, False, False, False]
    assert ev(df, "cal", "contiene", "P") == [False, False, False, True]


def test_list_ops_and_product(df):
    assert data_loader.list_columns(df) == ["lista"]
    assert ev(df, "lista", "contiene", "Y") == [True, False, True, False]
    assert ev(df, "lista", "contiene", "$producto", product="Z") == [False, False, False, True]
    assert ev(df, "lista", "no_en", "Y") == [False, True, False, True]
    assert ev(df, "lista", "==", "") == [False, True, False, False]  # empty list


def test_constants_as_attributes(df):
    consts = {"K_i": np.array([1.0, 0, 0, 1]), "KP_i": np.array([[0, 1], [0, 1], [1, 0], [1, 0]], float)}
    assert ev(df, "K_i", "==", "1", consts=consts) == [True, False, False, True]
    assert ev(df, "KP_i", "==", "1", consts=consts) == [False, False, True, True]  # campaign 0


def test_y_o_precedence(df):
    conds = [Condition("edad", "<", "30"), Condition("cal", "==", "A", "O"), Condition("flag", "==", "1", "Y")]
    # edad<30 O (cal==A Y flag==1)
    assert evaluate_all(conds, EvalContext(df)).tolist() == [True, False, False, False]


def test_errors_are_spanish_not_crashes(df):
    with pytest.raises(ExpressionError, match="no es una columna"):
        ev(df, "no_existe", "==", "1")
    with pytest.raises(ExpressionError, match="no es un número"):
        ev(df, "edad", "<", "abc")
    with pytest.raises(ExpressionError, match="no es numérica"):
        ev(df, "cal", "<", "3")
    with pytest.raises(ExpressionError, match="producto"):
        ev(df, "lista", "contiene", "$producto")
    errs = check_condition(Condition("edad", "~", "1"), set(df.columns), set(), [])
    assert errs and "desconocido" in errs[0]
