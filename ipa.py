import re

def ipaToSpell(w):
    """IPA記号を簡略化されたスペルに変換する関数"""
    # 母音
    w = re.sub(r"`|ˈ|ˌ", r"", w)
    w = re.sub(r"i|ɨ", r"i", w)
    w = re.sub(r"e|ɘ|e̞|ɛ|æ|ɜ|ɐ|œ|ɪ|ɪ̈", r"e", w)
    w = w.replace('ə', '(e|o)')
    w = w.replace('ɐ', '(e|a)')
    w = re.sub(r"ʊ|ø̞|o|ɤ̞|o̞|ʌ|ɔ", r"o", w)
    w = re.sub(r"a|ɶ|ä|ɑ|ɒ", r"a", w)
    w = re.sub(r"y|ʉ|ɯ|u|ʏ|ʊ̈|ɯ̽", r"u", w)

    # 子音
    w = re.sub(r"p|p̪", r"p", w)
    w = re.sub(r"t|t̪", r"t", w)
    w = re.sub(r"ʈ|c", r"t'", w)
    w = re.sub(r"k", r"k", w)
    w = re.sub(r"b|b̪", r"b", w)
    w = re.sub(r"d̪|d", r"d", w)
    w = re.sub(r"ɖ|ɟ", r"d'", w)
    w = re.sub(r"g", r"g", w)
    w = re.sub(r"m̥|m|ɱ̊|ɱ", r"m", w)
    w = re.sub(r"n̪̊|n̪|n̥|n", r"n", w)
    w = re.sub(r"ɳ|ɲ", r"n'", w)
    w = re.sub(r"ŋ", r"g", w)
    w = re.sub(r"r̥|r|ɹ̥|ɹ", r"r'", w)
    w = re.sub(r"ⱱ̟|ⱱ|ɸ|f|β̞|ʋ̥|ʋ", r"f", w)
    w = re.sub(r"ɾ|ɽ|ɟ̆", r"r", w)
    w = re.sub(r"β|v", r"v", w)
    w = re.sub(r"θ|s|ʃ", r"s", w)
    w = re.sub(r"ð|z|ʒ", r"z", w)
    w = re.sub(r"ʂ|ç|x", r"s'", w)
    w = re.sub(r"ʐ|ʝ|ɣ", r"z'", w)
    w = re.sub(r"χ", r"h", w)
    w = re.sub(r"ʁ", r"g", w)
    
    return w


def convert_ipa(ipa_text):
    """
    IPA文字列を変換する関数
    
    Parameters:
    ipa_text (str): 変換するIPA文字列
    
    Returns:
    tuple: (元のIPA, 変換後の文字列)
    """
    original = ipa_text
    converted = ipaToSpell(ipa_text)
    return original, converted


def interactive_mode():
    """対話モードで変換を実行"""
    print("IPA to Spell Converter")
    print("終了するには 'exit' と入力してください")
    print("=" * 40)
    
    while True:
        word = input('IPA: ')
        
        if word.lower() == "exit":
            print("終了します")
            break
        
        original, converted = convert_ipa(word)
        print(f"元のIPA: {original}")
        print(f"変換後: {converted}")
        print('-' * 40)


# 使用例
if __name__ == "__main__":
    # 関数として使用する例
    test_ipa = "ˈhɛloʊ"
    original, converted = convert_ipa(test_ipa)
    print(f"テスト変換:")
    print(f"  入力: {original}")
    print(f"  出力: {converted}")
    print()
    
    # 対話モードを起動
    interactive_mode()