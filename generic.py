# Generic function: text_maze_solver
# Solves a maze represented as a list of strings using DFS and prints the path
# Deliberate semantic error: The function does not mark visited cells, so it may revisit cells and get stuck in infinite recursion for cyclic mazes


def text_maze_solver(maze, start, end):
    """
    Solves a maze represented as a list of strings using DFS.

    Args:
            maze: List of strings, each string is a row of the maze.
                      Walls are '#', open spaces are ' '.
            start: Tuple (row, col) for the start position.
            end: Tuple (row, col) for the end position.

    Returns:
            List of positions representing the path from start to end, or None if no path.

    Example:
            maze = [
                    "########",
                    "#      #",
                    "# #### #",
                    "# #  # #",
                    "# ## # #",
                    "#    # #",
                    "########"
            ]
            path = text_maze_solver(maze, (1, 1), (5, 6))
            print(path)
    """
    rows = len(maze)
    cols = len(maze[0]) if rows > 0 else 0

    def dfs(pos, path):
        r, c = pos
        if r < 0 or r >= rows or c < 0 or c >= cols:
            return None
        if maze[r][c] == "#":
            return None
        if pos == end:
            return path + [pos]
        # SEMANTIC ERROR: Should mark visited cells, but does not
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            next_pos = (r + dr, c + dc)
            if next_pos in path:
                continue
            result = dfs(next_pos, path + [pos])
            if result:
                return result
        return None

    return dfs(start, [])


def demo_text_maze_solver():
    """
    Demo for text_maze_solver function.

    Args:
            None

    Returns:
            None

    Example:
            demo_text_maze_solver()
    """
    maze = [
        "########",
        "#      #",
        "# #### #",
        "# #  # #",
        "# ## # #",
        "#    # #",
        "########",
    ]
    start = (1, 1)
    end = (5, 6)
    path = text_maze_solver(maze, start, end)
    print("Maze:")
    for row in maze:
        print(row)
    print("Path:", path)
