// 자동 생성 파일: python web_build.py 로 다시 만든다(직접 고치지 말 것).
export const ENZYMES = [
  "CYP1A2",
  "CYP2B6",
  "CYP2C8",
  "CYP2C9",
  "CYP2C19",
  "CYP2D6",
  "CYP3A"
];

export const CONFIG = {
  "judgement": {
    "b0_small": 0.05,
    "ratio_up": 1.05,
    "ratio_down": 0.95,
    "diff_small": 0.05,
    "cause_min": 0.05
  },
  "flag": {
    "r_high": 1.25,
    "r_low": 0.8
  }
};

export const DEMO_SET = {
  "drugs": [
    {
      "name": "가상약A",
      "metabolism": {
        "CYP3A": {
          "f": 0.3,
          "g": 0.2,
          "source": "virtual"
        }
      },
      "inhibits": {
        "CYP3A": {
          "s": 0.6,
          "t": 0.8,
          "source": "virtual"
        }
      },
      "actions": {
        "P1": {
          "type": "agonist",
          "e": 0.3,
          "source": "virtual"
        }
      }
    },
    {
      "name": "가상약B",
      "metabolism": {
        "CYP3A": {
          "f": 0.7,
          "g": 0.5,
          "source": "virtual"
        }
      },
      "actions": {
        "P1": {
          "type": "agonist",
          "e": 0.4,
          "source": "virtual"
        },
        "P3": {
          "type": "agonist",
          "c": 0.5,
          "source": "virtual"
        }
      }
    },
    {
      "name": "가상약C",
      "metabolism": {
        "CYP2C19": {
          "f": 0.6,
          "g": 0.0,
          "source": "virtual"
        },
        "CYP3A": {
          "f": 0.2,
          "g": 0.1,
          "source": "virtual"
        }
      },
      "actions": {
        "P2": {
          "type": "agonist",
          "c": 0.3,
          "source": "virtual"
        }
      }
    },
    {
      "name": "가상약D",
      "dose_ratio": 2,
      "metabolism": {
        "CYP2D6": {
          "f": 0.8,
          "g": 0.0,
          "source": "virtual"
        }
      },
      "induces": {
        "CYP2C19": {
          "u": 1.0,
          "source": "virtual"
        }
      },
      "actions": {
        "P3": {
          "type": "antagonist",
          "c": 0.5,
          "source": "virtual"
        },
        "P4": {
          "type": "agonist",
          "c": 0.2,
          "source": "virtual"
        }
      }
    }
  ],
  "rules": {
    "effects": {
      "효과X": {
        "up": [
          "P1",
          "P2"
        ],
        "down": [],
        "k": 3.0,
        "threshold": 0.7,
        "source": "virtual"
      },
      "효과Y": {
        "up": [
          "P3"
        ],
        "down": [
          "P4"
        ],
        "k": 1.0,
        "threshold": null,
        "source": "virtual"
      }
    }
  }
};
