import re

def strip(w):
    """大文字や語頭、語末文字の削除"""
    x = w.replace('#', '')
    x = x.replace('φ', '')
    x = x.replace('e', '(a|i)')
    x = x.replace('o', '(e|a)')
    x = x.replace('q', '(b|u)')
    x = x.replace('x', "(sa|s'i)")
    x = x.replace('l', "(r'a|ri)")
    x = x.lower()
    return x

def ortho1(w):
    """前処理イジェール語正書法への適合"""
    x = w.translate(str.maketrans('AIUEO', '12345'))
    x = x.lower()
    x = x.translate(str.maketrans('12345', 'AIUEO'))
    x = x.replace('ki', 'kyi')
    x = x.replace('kI', 'kyI')
    x = x.replace('sh', 'sy')
    x = x.replace('si', 'syi')
    x = x.replace('sI', 'syI')
    x = x.replace('ti', 'tyi')
    x = x.replace('tI', 'tyI')
    x = x.replace('ch', 'ty')
    x = x.replace('ts', 'c')
    x = x.replace('tu', 'cu')
    x = x.replace('tU', 'cU')
    x = x.replace('fu', 'hu')
    x = x.replace('fU', 'hU')
    x = x.replace('dh', 'dy')
    x = x.replace('j', 'zy')
    return x

def ortho2(w):
    """後処理イジェール語正書法への適合"""
    p = re.compile("([stnzdbrSTNZDBR])y")
    x = p.sub(r"\1'", w)
    x = x.replace('#y', '#i')
    x = x.translate(str.maketrans('yw', 'iu'))
    return x

def commonf(w):
    x = w.replace('#hu', '#fu')
    p = re.compile("(\#)h([^y])")
    x = p.sub(r"\1\2", x)
    x = x.translate(str.maketrans('AIUEO', 'EAOIU'))
    x = x.translate(str.maketrans('aiueo', 'uiaeo'))
    p = re.compile("([^c])uφ")
    x = p.sub(r"\1φ", x)
    return x

def commone(w):
    x = w.replace('#hu', '#fu')
    p = re.compile("(\#)h([^y])")
    x = p.sub(r"\1\2", x)
    x = x.translate(str.maketrans('AIUEO', 'EAOIU'))
    x = x.translate(str.maketrans('aiueo', 'uiaeo'))
    p = re.compile("([^c])uφ")
    x = p.sub(r"\1eφ", x)
    return x

def sekore(w):
    """旗艦方言(Sekore)への変換"""
    # C1強勢時
    p = re.compile("h([AIUEO])")
    x = p.sub(r"F\1", w)
    p = re.compile("r(y*?)([AIUEO])")
    x = p.sub(r"D\1\2", x)
    # C2強勢時
    p = re.compile("([AIUEO])[uw]")
    x = p.sub(r"\1V", x)
    p = re.compile("([AIUEO])t")
    x = p.sub(r"\1C", x)
    p = re.compile("([AIUEO])r")
    x = p.sub(r"\1D", x)
    # 強勢VC後C1
    p = re.compile("([AIUEO])[sc]")
    x = p.sub(r"\1Z", x)
    p = re.compile("([AIUEO])t")
    x = p.sub(r"\1D", x)
    p = re.compile("([AIUEO])f")
    x = p.sub(r"\1V", x)
    p = re.compile("([AIUEO])[kh]")
    x = p.sub(r"\1G", x)
    p = re.compile("([AIUEO])p")
    x = p.sub(r"\1B", x)
    # C1の子音変化
    p = re.compile("p(y*?)([aiueo])")
    x = p.sub(r"f\1\2", x)
    p = re.compile("v(y*?)([aiueo])")
    x = p.sub(r"u\1\2", x)
    p = re.compile("d(y*?)([aiueo])")
    x = p.sub(r"r\1\2", x)
    p = re.compile("[kg](y*?)([aiueo])")
    x = p.sub(r"h\1\2", x)
    # C2の子音変化
    p = re.compile("([aiueo])f")
    x = p.sub(r"\1p", x)
    p = re.compile("([aiueo])[td]")
    x = p.sub(r"\1r", x)
    p = re.compile("([aiueo])v")
    x = p.sub(r"\1u", x)
    p = re.compile("([aiueo])g")
    x = p.sub(r"\1h", x)
    # 強勢のない半母音の母音化
    p = re.compile("[y']([^AIUEO])")
    x = p.sub(r"\1", x)
    # ts-->c
    p = re.compile("[tT][sS]")
    x = p.sub(r"c", x)
    x = ortho2(x)
    x = strip(x)
    return x

def titauini(w):
    """資源循環艦方言(Titauini)への変換"""
    # 3母音化
    x = w.translate(str.maketrans('oOE', 'eUI'))
    # C2強勢時
    x = w.translate(str.maketrans('jdbw', 'drwq'))
    x = ortho2(x)
    x = strip(x)
    return x

def kaiko(w):
    """探査艦方言(Kaiko)への変換"""
    # s,r変化
    p = re.compile("s([ieIE])")
    x = p.sub(r"sy\1", w)
    x = x.replace('se', 'x')
    p = re.compile("r([auAU])")
    x = p.sub(r"ry\1", x)
    x = x.replace('ro', 'l')
    # 強勢音節母音変化
    x = x.replace('Easi', 'AU')
    x = x.replace('A', 'AI')
    x = x.replace('O', 'EI')
    x = x.replace('U', 'OU')
    # 語末子音削除
    p = re.compile("[^aiueoAIUEO]φ")
    x = p.sub(r"φ", x)
    # 子音変化
    p = re.compile("g([aiueoAIUEO])")
    x = p.sub(r"ny\1", x)
    x = x.translate(str.maketrans('vh', 'uu'))
    x = x.replace('zy', 'i')
    # 連続子音変化
    p = re.compile("[^aiueoAIUEOxly#]([^aiueoAIUEOxly])")
    x = p.sub(r"\1\1", x)
    p = re.compile("[^aiueoAIUEOxly#]x")
    x = p.sub(r"sx", x)
    p = re.compile("[^aiueoAIUEOxly#]l")
    x = p.sub(r"rl", x)
    x = ortho2(x)
    x = strip(x)
    return x

def arzafire(w):
    """教団暗号(Arzafire)への変換準備"""
    x = w.translate(str.maketrans('aiueoAIUEO', 'iueoaIUEOA'))
    x = x.translate(str.maketrans('kstnhmyrwgzdbp', 'stnhmrrrkzdbgp'))
    x = x.replace('pr', 'py')
    x = x.replace('sr', 'sy')
    x = x.replace('nr', 'ny')
    x = x.replace('hr', 'hy')
    x = x.replace('mr', 'my')
    x = x.replace('rr', 'ry')
    x = x.replace('zr', 'zy')
    x = x.replace('dr', 'dy')
    x = x.replace('gr', 'gy')
    return x

def convert_idyer(word):
    """
    イジェール語の単語を各方言に変換する
    
    Args:
        word (str): 元単語（アクセントは大文字で指定）
        
    Returns:
        dict: 各方言の変換結果を含む辞書
            - 'sekore': 旗艦方言
            - 'titauini': 資源循環艦方言
            - 'kaiko': 探査艦方言
            - 'arzafire': 教団暗号
    """
    # 前処理
    processed_word = '#' + word + 'φ'
    processed_word = ortho1(processed_word)
    
    # 各方言への変換
    result = {}
    
    # commoneとcommonfの結果が同じかチェック
    ce = commone(processed_word)
    cf = commonf(processed_word)
    
    if ce == cf:
        result['sekore'] = sekore(ce)
        result['titauini'] = titauini(ce)
        result['kaiko'] = kaiko(ce)
    else:
        result['sekore'] = f"{sekore(ce)}または{sekore(cf)}"
        result['titauini'] = f"{titauini(ce)}または{titauini(cf)}"
        result['kaiko'] = f"{kaiko(ce)}または{kaiko(cf)}"
    
    # Arzafire変換
    arzafire_word = arzafire(processed_word)
    ce_arza = commone(arzafire_word)
    cf_arza = commonf(arzafire_word)
    
    if ce_arza == cf_arza:
        result['arzafire'] = sekore(ce_arza)
    else:
        result['arzafire'] = f"{sekore(ce_arza)}または{sekore(cf_arza)}"
    
    return result


# 使用例
if __name__ == "__main__":
    # 対話モード
    # print("イジェール語方言変換ツール")
    print("終了するには Ctrl+C を押してください\n")
    
    while True:
        try:
            word = input('元単語（アクセントは大文字）: ')
            if not word:
                continue
                
            result = convert_dialect(word)
            
            print(f"旗艦方言(Sekore)        : {result['sekore']}")
            print(f"資源循環艦方言(Titauini): {result['titauini']}")
            print(f"探査艦方言(Kaiko)       : {result['kaiko']}")
            print(f"教団暗号(Arzafire)      : {result['arzafire']}")
            print('---------------------------')
        except KeyboardInterrupt:
            print("\n終了します")
            break
        except Exception as e:
            print(f"エラー: {e}")