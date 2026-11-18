"""A printed word split where the text layer keeps it whole is not the layer's text (margins._splits_word); a layer
split into letters and printed joined is the same text."""
from mineru_plus import margins as M


def test_split_page_number_is_not_the_layer_word():
    # 11-18, PTA-129 MOESM1: page numbers '1 2' and '1 7' against the layers '12' and '17'
    assert M._splits_word(["12"], "1 2")
    assert M._splits_word(["17"], "1 7")


def test_letter_spaced_layer_against_joined_print_is_the_same_text():
    assert not M._splits_word(["J", "O", "U", "R", "N", "A", "L"], "JOURNAL")


def test_joined_layer_against_letter_spaced_print_is_split():
    assert M._splits_word(["JOURNAL"], "J O U R N A L")
