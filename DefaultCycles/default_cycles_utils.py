from ReinforcementLearning import Environment

t = 15


def fixed_cycle_action(simulation, dummy=None) -> bool:
    """ Returns a boolean indicating to take an action
    if the enough time elapsed since previous action """
    switch = False
    time_elapsed = simulation.t - simulation.traffic_signals[0].prev_update_time >= t
    if time_elapsed:
        simulation.traffic_signals[0].prev_update_time = simulation.t
        switch = True
    return switch


def longest_queue_action(simulation, state) -> bool:
    """ Returns a boolean indicating to take an action
    if the enough time elapsed since previous action """
    switch = False
    time_elapsed = simulation.t - simulation.traffic_signals[0].prev_update_time >= t
    if time_elapsed:
        west_east_signal_state, n_west_east_vehicles, n_south_north_vehicles, non_empty_junction = state
        if west_east_signal_state and n_west_east_vehicles < n_south_north_vehicles:
            switch = True
        elif not west_east_signal_state and n_west_east_vehicles > n_south_north_vehicles:
            switch = True
    if switch:
        simulation.traffic_signals[0].prev_update_time = simulation.t
    return switch


action_funcs = {'fc': fixed_cycle_action,
                'lqf': longest_queue_action}


def default_cycle(n_episodes: int, action_func_name: str, render):
    print(f"\n -- Running FC for {n_episodes} episodes  -- ")
    environment: Environment = Environment()
    total_wait_time, total_collisions = 0, 0
    action_func = action_funcs[action_func_name]
    for episode in range(1, n_episodes + 1):
        state = environment.reset(render)
        score = 0
        collision_detected = 0
        done = False

        while not done:
            action = action_func(environment.sim, state)
            state, reward, done, truncated = environment.step(action)
            if truncated:
                exit()
            score += reward
            collision_detected += environment.sim.collision_detected

        if collision_detected:
            print(f"Episode {episode} - Collisions: {int(collision_detected)}")
            total_collisions += 1
        else:
            wait_time = environment.sim.current_average_wait_time
            total_wait_time += wait_time
            print(f"Episode {episode} - Wait time: {wait_time:.2f}")

    n_completed = n_episodes - total_collisions
    print(f"\n -- Results after {n_episodes} episodes: -- ")
    print(
        f"Average wait time per completed episode: {total_wait_time / n_completed:.2f}")
    print(f"Average collisions per episode: {total_collisions / n_episodes:.2f}")
