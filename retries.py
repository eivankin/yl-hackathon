import json
import time
from multiprocessing import Process
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from itertools import product

target = None
map_size = 30
ship_size = 2


def print_data(data: 'JSONCapability') -> None:
    data.Message = f'Total retries count: {retries_count}'
    print(json.dumps(data, default=lambda x: x.to_json(), ensure_ascii=False))


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
    FireInfos: List[FireInfo]
    My: List[Ship]
    Opponent: List[Ship]

    @classmethod
    def from_json(cls, data):
        my = list(map(Ship.from_json, data['My']))
        opponent = list(map(Ship.from_json, data['Opponent']))
        fire_infos = list(map(FireInfo.from_json, data['FireInfos']))
        return cls(fire_infos, my, opponent)


# endregion


def make_draft(data: dict) -> dict:
    global player_id
    player_id = int(data['PlayerId'])
    return {}


def make_turn(data: dict, callback) -> None:
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
    for p in product(range(-ship_size, 1), repeat=3):
        dv = Vector(*p)
        pos_black_list |= {fire.Target + dv for fire in battle_state.FireInfos}

    non_target = enemies - {target}

    for ship in battle_state.My:
        engine = next(filter(lambda e: isinstance(e, EngineBlock), ship.Equipment), None)
        if engine is not None:
            step = engine.MaxAccelerate

            positions_set = set(filter(
                Vector.in_bounds,
                map(lambda v: ship.Position + Vector(*v), product((0, step, -step), repeat=3)))
            ) - pos_black_list - moves

            if positions_set:
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

        for gun in filter(lambda e: isinstance(e, GunBlock), ship.Equipment):
            aim = None
            r = gun.Radius

            if ship.Position.clen(target.Position + target.Velocity) <= r + ship_size:
                aim = target.Position + target.Velocity

            else:
                opponents = [
                    opponent for opponent in non_target
                    if ship.Position.clen(opponent.Position + opponent.Velocity) <= r + ship_size
                ]
                if opponents:
                    opponent = min(opponents, key=lambda o: o.Health)
                    aim = opponent.Position + opponent.Velocity

            if aim is not None:
                battle_output.UserCommands.append(
                    UserCommand(
                        Command='ATTACK', Parameters=AttackCommandParameters(ship.Id, gun.Name, aim)
                    )
                )
    callback(battle_output)


def play_game():
    global retries_count
    # print_data(make_draft(json.loads(input())))
    print('{}')
    while True:
        p = Process(target=make_turn, args=(json.loads(input()), print_data))
        p.start()
        cumtime = 0
        curr_time = 0
        while True:
            if not p.is_alive():
                break
            if p.is_alive() and cumtime + curr_time > 0.8:
                print('{"Message": "Oh no"}')
                p.kill()
                break
            if p.is_alive() and curr_time > 0:
                cumtime += curr_time
                curr_time = 0
                p.kill()
                p.start()
                retries_count += 1
            time.sleep(0.1)
            curr_time += 0.1


if __name__ == '__main__':
    retries_count = 0
    player_id = 0
    play_game()