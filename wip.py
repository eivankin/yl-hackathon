"""Ломается на стадии draft в тестирующей системе"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class JSONCapability:
    def to_json(self):
        return {
            k: v if not isinstance(v, Vector) else str(v)
            for k, v in self.__dict__.items() if v is not None
        }


@dataclass
class Vector:
    X: int
    Y: int
    Z: int

    @classmethod
    def from_json(cls, data):
        x, y, z = map(int, data.split('/'))
        return cls(x, y, z)

    def __str__(self):
        return f"{self.X}/{self.Y}/{self.Z}"

    def __add__(self, other: 'Vector'):
        return Vector(self.X + other.X, self.Y + other.Y, self.Z + other.Z)

    def __sub__(self, other: 'Vector'):
        return self + other * -1

    def __mul__(self, coefficient: int):
        return Vector(self.X * coefficient, self.Y * coefficient, self.Z * coefficient)

    def clen(self, other: 'Vector'):
        return max(abs(self.X - other.X), abs(self.Y - other.Y), abs(self.Z - other.Z))


class EquipmentType(Enum):
    Energy = 0
    Gun = 1
    Engine = 2
    Health = 3


class EffectType(Enum):
    Blaster = 0


@dataclass
class EquipmentBlock(JSONCapability):
    Name: str
    Type: EquipmentType

    @classmethod
    def from_json(cls, data):
        if EquipmentType(data['Type']) == EquipmentType.Energy:
            return EnergyBlock(**data)
        elif EquipmentType(data['Type']) == EquipmentType.Gun:
            return GunBlock(**data)
        elif EquipmentType(data['Type']) == EquipmentType.Engine:
            return EngineBlock(**data)
        elif EquipmentType(data['Type']) == EquipmentType.Health:
            return HealthBlock(**data)


@dataclass
class DraftEquipment:
    Size: int
    Equipment: EquipmentBlock

    @classmethod
    def from_json(cls, data: dict):
        data['Equipment'] = EquipmentBlock.from_json(data['Equipment'])
        return cls(**data)


@dataclass
class EnergyBlock(EquipmentBlock):
    IncrementPerTurn: int
    MaxEnergy: int
    StartEnergy: int
    Type = EquipmentType.Energy


@dataclass
class EngineBlock(EquipmentBlock):
    MaxAccelerate: int
    Type = EquipmentType.Engine


@dataclass
class GunBlock(EquipmentBlock):
    Damage: int
    EffectType: EffectType
    EnergyPrice: int
    Radius: int
    Type = EquipmentType.Gun


@dataclass
class HealthBlock(EquipmentBlock):
    MaxHealth: int
    StartHealth: int


@dataclass
class EffectType(EquipmentBlock):
    MaxHealth: int
    StartHealth: int
    Type = EquipmentType.Health


@dataclass
class CommandParameters(JSONCapability):
    pass


@dataclass
class AttackCommandParameters(CommandParameters):
    Id: int
    Name: str
    Target: Vector


@dataclass
class MoveCommandParameters(CommandParameters):
    Id: int
    Target: Vector


@dataclass
class AccelerateCommandParameters(CommandParameters):
    Id: int
    Vector: Vector


@dataclass
class UserCommand(JSONCapability):
    Command: str
    Parameters: CommandParameters


@dataclass
class BattleOutput(JSONCapability):
    Message: str = None
    UserCommands: List[UserCommand] = None


@dataclass
class Ship(JSONCapability):
    Id: int
    Position: Vector
    Velocity: Vector
    Energy: Optional[int] = None
    Health: Optional[int] = None
    Equipment: List[EquipmentBlock] = None

    @classmethod
    def from_json(cls, data):
        if data.get('Equipment'):
            data['Equipment'] = list(map(EquipmentBlock.from_json, data.get('Equipment', [])))
        data['Position'] = Vector.from_json(data['Position'])
        data['Velocity'] = Vector.from_json(data['Velocity'])
        return cls(**data)


@dataclass
class FireInfo(JSONCapability):
    EffectType: EffectType
    Source: Vector
    Target: Vector

    @classmethod
    def from_json(cls, data):
        data['Source'] = Vector.from_json(data['Source'])
        data['Target'] = Vector.from_json(data['Target'])
        return cls(**data)


@dataclass
class BattleState(JSONCapability):
    FireInfos: List[FireInfo]
    My: List[Ship]
    Opponent: List[Ship]

    @classmethod
    def from_json(cls, data):
        my = list(map(Ship.from_json, data['My']))
        opponent = list(map(Ship.from_json, data['Opponent']))
        fire_infos = list(map(FireInfo.from_json, data['FireInfos']))
        return cls(fire_infos, my, opponent)


@dataclass
class DraftChoice(JSONCapability):
    Ships: Optional[List['DraftShipChoice']] = None
    Message: Optional[str] = None


@dataclass
class DraftCompleteShip:
    Id: str
    Price: int
    Equipment: List[str]


@dataclass
class DraftOptions:
    PlayerId: int
    MapSize: int
    Money: int
    MaxShipsCount: int
    # DraftTimeout: int
    # BattleRoundTimeout: int
    StartArea: dict[str, Vector]
    Equipment: List[DraftEquipment]
    CompleteShips: List[DraftCompleteShip]

    @classmethod
    def from_json(cls, data):
        data['CompleteShips'] = [DraftCompleteShip(**ship) for ship in data['CompleteShips']]
        data['StartArea'] = {k: Vector.from_json(v) for k, v in data['StartArea'].items()}
        data['Equipment'] = [DraftEquipment.from_json(equip) for equip in data['Equipment']]
        return cls(**data)


@dataclass
class DraftShipChoice(JSONCapability):
    Position: Vector
    CompleteShipId: str


def make_draft(data: dict) -> DraftChoice:
    global draft_options

    draft_options = DraftOptions.from_json(data)
    ship = draft_options.CompleteShips[0]
    draft_choice = DraftChoice()
    draft_choice.Ships = []
    ship_count = min(draft_options.Money // max(ship.Price, 1), draft_options.MaxShipsCount)
    ship_size = int(len(ship.Equipment) ** 0.5) + 1

    vector_from, vector_to = draft_options.StartArea['From'], draft_options.StartArea['To']
    min_y, min_z = min(vector_from.Y, vector_to.Y), min(vector_from.Z, vector_to.Z)

    for i in range(ship_count):
        draft_choice.Ships.append(
            DraftShipChoice(Vector(draft_options.MapSize // 2 - ((ship_count // 2 - i) * ship_size),
                                   min_y, min_z), ship.Id)
        )
    return draft_choice


def make_turn(data: dict) -> BattleOutput:
    battle_state = BattleState.from_json(data)
    battle_output = BattleOutput()
    battle_output.Message = f"I have {len(battle_state.My)} " \
                            f"ships and move to center of galaxy and shoot"
    battle_output.UserCommands = []

    for ship in battle_state.My:
        battle_output.UserCommands.append(
            UserCommand(
                Command="MOVE", Parameters=MoveCommandParameters(
                    ship.Id, Vector(ship.Position.X, 15, 10)
                )
            )
        )
        guns = [x for x in ship.Equipment if isinstance(x, GunBlock)]
        for gun in guns:
            opponents = [opponent for opponent in battle_state.Opponent if
                         ship.Position.clen(opponent.Position) <= gun.Radius]
            if opponents:
                battle_output.UserCommands.append(
                    UserCommand(
                        Command="ATTACK", Parameters=AttackCommandParameters(
                            ship.Id, gun.Name, opponents[0].Position + opponents[0].Velocity
                        )
                    )
                )
    return battle_output


def play_game():
    while True:
        raw_line = input()
        line = json.loads(raw_line)
        if 'PlayerId' in line:
            print(json.dumps(make_draft(line), default=lambda x: x.to_json(), ensure_ascii=False))
        elif 'My' in line:
            print(json.dumps(make_turn(line), default=lambda x: x.to_json(), ensure_ascii=False))


if __name__ == '__main__':
    draft_options = None
    play_game()
