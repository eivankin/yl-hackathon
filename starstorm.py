import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from itertools import product

target = None
map_size = 30
ship_size = 2


class JSONCapability:
    def to_json(self):
        return {
            k: v if not isinstance(v, Vector) else str(v)
            for k, v in self.__dict__.items() if v is not None
        }


# region primitives
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
        return f'{self.X}/{self.Y}/{self.Z}'

    def __add__(self, other: 'Vector'):
        return Vector(self.X + other.X, self.Y + other.Y, self.Z + other.Z)

    def __sub__(self, other: 'Vector'):
        return self + other * -1

    def __mul__(self, coefficient: int) -> 'Vector':
        return Vector(self.X * coefficient, self.Y * coefficient, self.Z * coefficient)

    def clen(self, other: 'Vector') -> int:
        return max(abs(self.X - other.X), abs(self.Y - other.Y), abs(self.Z - other.Z))

    def __hash__(self):
        return hash((self.X, self.Y, self.Z))

    def __eq__(self, other: 'Vector') -> bool:
        return (self.X, self.Y, self.Z) == (other.X, other.Y, other.Z)

    def in_bounds(self) -> bool:
        return all(all(0 < c + d < map_size for d in range(3)) for c in (self.X, self.Y, self.Z))


# endregion

# region battle commands

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


# endregion

# region equipment

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
        if EquipmentType(data['Type']) == EquipmentType.Gun:
            return GunBlock(**data)
        if EquipmentType(data['Type']) == EquipmentType.Engine:
            return EngineBlock(**data)
        if EquipmentType(data['Type']) == EquipmentType.Health:
            return HealthBlock(**data)


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


# endregion

# region battle state

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

    def __eq__(self, other: 'Ship') -> bool:
        return self.Id == other.Id

    def __hash__(self):
        return hash(self.Id)


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
    # FireInfos: List[FireInfo]
    My: List[Ship]
    Opponent: List[Ship]

    @classmethod
    def from_json(cls, data):
        my = list(map(Ship.from_json, data['My']))
        opponent = list(map(Ship.from_json, data['Opponent']))
        # fire_infos = list(map(FireInfo.from_json, data['FireInfos']))
        return cls(my, opponent)


# endregion


def make_draft(data: dict) -> dict:
    result = {'Ships': []}
    money = int(data['Money'])
    max_count = 5
    prices = {s['Id']: int(s['Price']) for s in data['CompleteShips']}
    counts = [0, 0]
    for i in range(max_count):
        if money >= prices['starstorm'] + (max_count - i) * prices['scout']:
            result['Ships'].append({'CompleteShipId': 'starstorm', 'Position': None})
            money -= prices['starstorm']
            counts[0] += 1
        elif money >= prices['scout']:
            result['Ships'].append({'CompleteShipId': 'scout', 'Position': None})
            counts[1] += 1
            money -= prices['scout']
    result['Message'] = f'I have {counts[0]} starstorms and {counts[1]} scouts'
    return result


def make_turn(data: dict) -> BattleOutput:
    global target

    battle_state = BattleState.from_json(data)
    battle_output = BattleOutput()
    battle_output.UserCommands = []
    moves = set()

    enemies = set(battle_state.Opponent)
    if target is None or target not in battle_state.Opponent:
        target = min(enemies,
                     key=lambda o: (battle_state.My[0].Position.clen(o.Position), o.Health))
    else:
        # updating target position
        target = next(filter(lambda o: o == target, enemies))

    pos_black_list = set()
    # for p in product(range(-ship_size, 1), repeat=3):
    #     pos_black_list |= {fire.Target + Vector(*p) for fire in battle_state.FireInfos}

    non_target = enemies - {target}
    r = None

    for ship in battle_state.My:
        for gun in filter(lambda e: isinstance(e, GunBlock), ship.Equipment):
            aim = None
            r = gun.Radius

            if ship.Position.clen(target.Position) <= r + ship_size:
                aim = target.Position

            else:
                opponents = [
                    opponent for opponent in non_target
                    if ship.Position.clen(opponent.Position) <= r + ship_size
                ]
                if opponents:
                    opponent = min(opponents, key=lambda o: o.Health)
                    aim = opponent.Position

            if aim is not None:
                battle_output.UserCommands.append(
                    UserCommand(
                        Command='ATTACK', Parameters=AttackCommandParameters(ship.Id, gun.Name, aim)
                    )
                )

        engine = next(filter(lambda e: isinstance(e, EngineBlock), ship.Equipment), None)
        if engine is not None:
            step = engine.MaxAccelerate

            positions_set = set(filter(
                Vector.in_bounds,
                map(lambda v: ship.Position + Vector(*v), product((0, step, -step), repeat=3)))
            ) - pos_black_list - moves

            if positions_set:
                r = r or 5
                target_pos = min(
                    positions_set,
                    key=lambda v: abs(5 - target.Position.clen(v)) + sum(map(
                        lambda o: o.Position.clen(v) < 6, non_target
                    ))
                )
            else:
                target_pos = ship.Position

            moves |= set(map(lambda v: target_pos + Vector(*v),
                             product((0, 1, -1), repeat=3)))

            battle_output.UserCommands.append(
                UserCommand(
                    Command='MOVE', Parameters=MoveCommandParameters(ship.Id, target_pos)
                )
            )



    return battle_output


def play_game():
    global max_time, moves_count, max_time_move

    print(json.dumps(make_draft(json.loads(input())),
                     default=lambda x: x.to_json(), ensure_ascii=False))
    while True:
        raw = input()
        start_time = time.time()
        result_dict = make_turn(json.loads(raw))

        elapsed = (time.time() - start_time) * 1000

        if max_time is None or elapsed > max_time:
            max_time = elapsed
            max_time_move = moves_count

        result_dict.Message = f'Max time: {max_time:.3f} ms; max time move: {max_time_move}'
        print(json.dumps(result_dict, default=lambda x: x.to_json(), ensure_ascii=False))
        moves_count += 1


if __name__ == '__main__':
    max_time, max_time_move = None, 1
    moves_count = 1
    play_game()
