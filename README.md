# Primordial Age

This is the primordial land of Pangu. It was empty and formless but the principles of Yin and Yang have begun to work to generate the first stirrings of life. With the first life comes the struggle to improve, and to transcend. 


## Features
There are 5 principle elements in Pangu, with Yin and Yang aspects. 

- 5 Element types: Wood, Water, Metal, Fire, Earth

-- Wood corresponds with generation and growth
-- Fire corresponds with thinking and motion
-- Earth corresponds with substance and stability
-- Metal with hardness and attack
-- Water with willpower and motion

## Element Relationships
The elements relate to each other in both productive and destructive cucles 
### Productive Cycle
- Water produces Wood
- Wood produces Fire
- Fire produces Earth
- Earth produces Metal
- Metal produces Water

### Destructive Cycle
- Fire destroys Metal
- Metal destroys Wood
- Wood destroys Earth
- Earth destroys Water
- Water destroys Fire

## Resources and Hazards
After the primordial chaos in Pangyu, the first life and structure began to appear

### Resources
- Leaves (Wood)
- Melons (Water)
- Salt (Metal)
- Carrots (Fire)
- Potatoes (Earth)

### Hazards
- Thorns (Wood)
- Pools (Water)
- Spikes (Metal)
- Coals (Fire)
- Sand (Earth)

# Age of development
From the pieces of world combining and gaining substance, the first taobot monsters appeared. Composed of varying combinations of elements, in infinite patterns, the taobots rise, strive and fall, only to rise again, improving with each lifetime. In the age of development, hopeful monsters are spawned, most of whom are unable to sense, move, grow or reason in the world. Some very few show the signs of organisation, will and drive. These fitfully reproduce, and move towards sentience

The taobots are made of 5 parts, plus chi

- Legs: Water
- Meridians: Wood
- Nerves, eyes: Fire
- Body, mouth: Earth
- Armor, claws: Metal

The taobots move through the world, collecting elements and generating chi. When they have sufficient chi, they spawn. Spawned taobots are combinations of 2 parents, and have mutations in their characters.

We record each bots' genetic types in a bank, as well as their karma (fitness score). Bots with higher karma are more likely to respawn after death.

# Age of cultivation
There are now lineages of taobots with the skills and bodies to navigate their world. When they encounter each other they strive. Becoming more adept at resource collection, battling with their claws, and their essenced chi, they may consume each other, and rise higher


# Technical details


## Taobot details
Taobots are generated programatically from a genetic system. They are modelled on a circular scheme (polar coordinates) and body parts are arranged accordingly. Meridians are on the inside at specific locations, neurons have a start and end, and make connections at synapses at specific coordinates. Legs and eyes are around the outer edge. Symmetry can be radial or bilateral and this will determine how the body parts are generated (a single gene might code for a leg that appears at 6 evenly spaced locations around a six-symmetry taobot)

### Neurons
- the most complex and subtle structures.
- consumes fire essence
- relu activation function
- can be a delayed decay of activiation state before firing (accumulate multiple stimuli)
- may have multiple dendrites, each with a radial coordinate
- the dendrites on the outside are eyes, and are stimulated by light from the environment
-- color vision 
-- ray casting?
- synapses can be inhibitory or stimulatory

### Legs
- triggered by neurons
- consume water chi to move
- assume motion vector with a magnitude generated proportional to water consumption, maybe forward or backward depending on wiring to neurons
- total taobot motion per turn is sum of all vectors

### Meridians
- consume wood essence
- a meridian can be any of the 5 elemental types
- the meridian volume is a genetic function (it takes actual space in the taobot) and determines how much they can hold
- meridians can synapse with neurons so can (eg) send oulses at a rate proportional to how empty the meridian is
--probaby need to be abe to form synapses of different types: absorb (element), diffuse (element), expel (element)
- meridians can detect the elemental chi balance in the internal chi
- they can form directed junctions with other meridians 
- when activated by neuron, junctions can release chi from one meridian into another
- meridians can have external junctions so can spit out elements 
- absorb and store their specific element
-- the rate that they absorb the element from the internal chi is proportional to the consumption of wood essence
- can diffuse out element into internal chi
-- the rate that they diffuse the element from the internal chi is proportional to the consumption of wood essence

### Body
- consume earth essemce
- all the body parts are made out of earth, and when they get damaged will need to be repaired by absorbing earth essence
- bigger body parts need more earth
- probably doesn't need its own gene-type, more like a factor required by the others

### Armor
- consume metal essence
- scales and claws can be grown on exterior of taobot
- location and size and shape specialised genetically
- have a certain amount of weight so probably don't want too much
- wear down and need to be replenished
- claws damage other taobots when collide, proportional to speed, claw size
- scales absorb damage


### Internal chi
- has an amount value
- can hold the elements at various proportions
- the organs can absorb elements that are present in the chi
- there is elemental chemistry, where elements that are present together in the chi will degrade each other according to the destructive cycle with a rate tbd
- note: the same chemistry relationships appliy in the meridians. If wood chi is injected into a fire meridian, the fire will be fed. If water chi were injected into the fire meridian, it'll dampen the fire


## Spawning details
- the genes for each taobot will be ordered in a file, each with a numeric identifier, and a bunch of domains tbd