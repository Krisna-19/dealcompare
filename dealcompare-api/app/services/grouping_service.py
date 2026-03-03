from utils.text_utils import similarity_score

def group_products(products):
    grouped = []
    used = set()

    for i, p1 in enumerate(products):
        if i in used:
            continue

        group = [p1]
        used.add(i)

        for j, p2 in enumerate(products):
            if j in used:
                continue

            score = similarity_score(p1.title, p2.title)

            if score > 0.6:   # similarity threshold
                group.append(p2)
                used.add(j)

        grouped.append(group)

    return grouped
